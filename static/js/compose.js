/* Progressive UI behaviors for the compose editor.
 *
 * Alpine component for recipient toggles (Cc/Bcc), Rich Text / Plain Text
 * toggling, formatting commands via document.execCommand, active button state
 * tracking via document.queryCommandState, and synchronization between
 * contenteditable and the form textarea.
 *
 * Recipient contact autocomplete activates when typing 3 or more characters in
 * a recipient field (To / Cc / Bcc) and uses the native `hidden` attribute so
 * it stays hidden by default without inline style mutations.
 */
(function () {
  "use strict";

  var MIN_CONTACT_SEARCH_CHARS = 3;
  var activeRecipientInput = null;

  function getSuggestionsContainer() {
    return document.getElementById("contact-suggestions");
  }

  function hideContactSuggestions() {
    var container = getSuggestionsContainer();
    if (container) {
      container.hidden = true;
    }
  }

  function extractLastToken(rawValue) {
    var parts = (rawValue || "").split(",");
    return (parts[parts.length - 1] || "").trim();
  }

  function updateContactSuggestions(inputEl) {
    var container = getSuggestionsContainer();
    if (!container || !(inputEl instanceof HTMLInputElement)) {
      return;
    }
    activeRecipientInput = inputEl;
    var token = extractLastToken(inputEl.value).toLowerCase();
    if (token.length < MIN_CONTACT_SEARCH_CHARS) {
      container.hidden = true;
      return;
    }

    var items = container.querySelectorAll("[data-contact-item]");
    var visibleCount = 0;
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      var haystack = (item.getAttribute("data-search") || "").toLowerCase();
      var matches = haystack.indexOf(token) !== -1;
      item.hidden = !matches;
      if (matches) {
        visibleCount += 1;
      }
    }
    container.hidden = visibleCount === 0;
  }

  function applyContactSelection(button) {
    if (!button || !(activeRecipientInput instanceof HTMLInputElement)) {
      return;
    }
    var address = (button.getAttribute("data-address") || "").trim();
    if (!address) {
      return;
    }

    var rawSegments = (activeRecipientInput.value || "").split(",");
    var kept = [];
    for (var i = 0; i < rawSegments.length - 1; i += 1) {
      var seg = rawSegments[i].trim();
      if (seg && kept.indexOf(seg) === -1) {
        kept.push(seg);
      }
    }
    if (kept.indexOf(address) === -1) {
      kept.push(address);
    }
    activeRecipientInput.value = kept.join(", ");
    hideContactSuggestions();
    activeRecipientInput.focus();
    activeRecipientInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("input", function (event) {
    var target = event.target;
    if (
      target instanceof HTMLInputElement &&
      target.hasAttribute("data-recipient-input")
    ) {
      updateContactSuggestions(target);
    }
  });

  document.addEventListener("focusin", function (event) {
    var target = event.target;
    if (
      target instanceof HTMLInputElement &&
      target.hasAttribute("data-recipient-input")
    ) {
      activeRecipientInput = target;
      updateContactSuggestions(target);
    }
  });

  document.addEventListener("mousedown", function (event) {
    if (!(event.target instanceof Element)) {
      return;
    }
    var contactBtn = event.target.closest("[data-contact-item]");
    if (contactBtn) {
      event.preventDefault();
      applyContactSelection(contactBtn);
      return;
    }
    if (!event.target.closest("[data-recipient-input]")) {
      hideContactSuggestions();
    }
  });

  document.addEventListener("keydown", function (event) {
    var container = getSuggestionsContainer();
    if (!container || container.hidden) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      hideContactSuggestions();
      return;
    }
    if (
      (event.key === "Enter" || event.key === "Tab") &&
      event.target instanceof HTMLInputElement &&
      event.target.hasAttribute("data-recipient-input")
    ) {
      var firstVisible = container.querySelector(
        "[data-contact-item]:not([hidden])",
      );
      if (firstVisible) {
        event.preventDefault();
        applyContactSelection(firstVisible);
      }
    }
  });

  document.addEventListener("alpine:init", function () {
    if (!window.Alpine) {
      return;
    }

    window.Alpine.data("composer", function () {
      return {
        showCc: false,
        showBcc: false,
        richText: true,
        isBold: false,
        isItalic: false,
        isUnderline: false,
        isStrike: false,
        isBullet: false,
        isNumbered: false,
        isLeft: false,
        isCenter: false,
        isRight: false,
        get isPlain() {
          return !this.richText;
        },
        init() {
          var ccInput = this.$refs.ccInput;
          if (ccInput && ccInput.value && ccInput.value.trim().length > 0) {
            this.showCc = true;
          }
          var bccInput = this.$refs.bccInput;
          if (bccInput && bccInput.value && bccInput.value.trim().length > 0) {
            this.showBcc = true;
          }
          this.initEditorContent();

          var self = this;
          document.addEventListener("selectionchange", function () {
            if (
              self.richText &&
              self.$refs.editor &&
              (document.activeElement === self.$refs.editor ||
                self.$refs.editor.contains(document.activeElement))
            ) {
              self.updateFormatState();
            }
          });
        },
        updateFormatState() {
          if (!this.richText || !this.$refs.editor) {
            return;
          }
          try {
            this.isBold = document.queryCommandState("bold");
            this.isItalic = document.queryCommandState("italic");
            this.isUnderline = document.queryCommandState("underline");
            this.isStrike = document.queryCommandState("strikeThrough");
            this.isBullet = document.queryCommandState("insertUnorderedList");
            this.isNumbered = document.queryCommandState("insertOrderedList");
            this.isLeft = document.queryCommandState("justifyLeft");
            this.isCenter = document.queryCommandState("justifyCenter");
            this.isRight = document.queryCommandState("justifyRight");
          } catch (e) {
            // queryCommandState can throw if selection is outside
          }
        },
        toggleCc() {
          this.showCc = !this.showCc;
          if (this.showCc && this.$refs.ccInput) {
            var self = this;
            window.setTimeout(function () {
              self.$refs.ccInput.focus();
            }, 50);
          }
        },
        toggleBcc() {
          this.showBcc = !this.showBcc;
          if (this.showBcc && this.$refs.bccInput) {
            var self = this;
            window.setTimeout(function () {
              self.$refs.bccInput.focus();
            }, 50);
          }
        },
        attachFile() {
          if (this.$refs.fileInput) {
            this.$refs.fileInput.click();
          }
        },
        toggleMode() {
          if (this.richText) {
            var text = this.getTextContent();
            this.$refs.bodyInput.value = text;
            this.richText = false;
            var self = this;
            window.setTimeout(function () {
              if (self.$refs.bodyInput) {
                self.$refs.bodyInput.focus();
              }
            }, 50);
          } else {
            var html = this.escapeHtmlToParagraphs(this.$refs.bodyInput.value);
            this.$refs.editor.innerHTML = html;
            this.richText = true;
            var self2 = this;
            window.setTimeout(function () {
              if (self2.$refs.editor) {
                self2.$refs.editor.focus();
                self2.updateFormatState();
              }
            }, 50);
          }
          this.triggerDraftAutosave();
        },
        bold() {
          this.format("bold");
        },
        italic() {
          this.format("italic");
        },
        underline() {
          this.format("underline");
        },
        strikeThrough() {
          this.format("strikeThrough");
        },
        bulletList() {
          this.format("insertUnorderedList");
        },
        numberedList() {
          this.format("insertOrderedList");
        },
        alignLeft() {
          this.format("justifyLeft");
        },
        alignCenter() {
          this.format("justifyCenter");
        },
        alignRight() {
          this.format("justifyRight");
        },
        clearFormat() {
          this.format("removeFormat");
        },
        format(command, value) {
          if (!this.richText) {
            return;
          }
          if (this.$refs.editor) {
            this.$refs.editor.focus();
          }
          document.execCommand(command, false, value || null);
          this.updateFormatState();
          this.syncToTextarea();
        },
        initEditorContent() {
          if (!this.$refs.editor || !this.$refs.bodyInput) {
            return;
          }
          var val = this.$refs.bodyInput.value || "";
          if (
            val &&
            !val.includes("<p>") &&
            !val.includes("<div>") &&
            !val.includes("<br>") &&
            !val.includes("<ul>") &&
            !val.includes("<ol>")
          ) {
            this.$refs.editor.innerHTML = this.escapeHtmlToParagraphs(val);
          } else {
            this.$refs.editor.innerHTML = val || "<p><br></p>";
          }
        },
        onEditorInput() {
          this.updateFormatState();
          this.syncToTextarea();
        },
        onEditorActivity() {
          this.updateFormatState();
        },
        syncToTextarea() {
          if (!this.$refs.editor || !this.$refs.bodyInput) {
            return;
          }
          var html = this.$refs.editor.innerHTML;
          if (html === "<p><br></p>" || html === "<br>" || html === "<p></p>") {
            html = "";
          }
          this.$refs.bodyInput.value = html;
          this.triggerDraftAutosave();
        },
        getTextContent() {
          if (!this.$refs.editor) {
            return "";
          }
          return this.$refs.editor.innerText || this.$refs.editor.textContent || "";
        },
        escapeHtmlToParagraphs(text) {
          if (!text) {
            return "<p><br></p>";
          }
          var lines = text.split(/\r?\n/);
          return lines
            .map(function (line) {
              var div = document.createElement("div");
              div.textContent = line;
              return "<p>" + (div.innerHTML || "<br>") + "</p>";
            })
            .join("");
        },
        triggerDraftAutosave() {
          if (this.$refs.bodyInput) {
            var event = new Event("input", { bubbles: true });
            this.$refs.bodyInput.dispatchEvent(event);
          }
        },
        openImageModal() {
          this.saveSelection();
          var fileInput = document.getElementById("compose-image-file-input");
          if (fileInput) {
            fileInput.value = "";
          }
          var urlInput = document.getElementById("compose-image-url-input");
          if (urlInput) {
            urlInput.value = "";
          }
          var dialog = document.getElementById("insert-image-modal");
          if (dialog && typeof dialog.showModal === "function") {
            dialog.showModal();
          }
        },
        closeImageModal() {
          var dialog = document.getElementById("insert-image-modal");
          if (dialog && typeof dialog.close === "function") {
            dialog.close();
          }
        },
        saveSelection() {
          var sel = window.getSelection();
          if (sel && sel.rangeCount > 0) {
            this._savedRange = sel.getRangeAt(0);
          }
        },
        restoreSelection() {
          if (this._savedRange && this.$refs.editor) {
            this.$refs.editor.focus();
            var sel = window.getSelection();
            if (sel) {
              sel.removeAllRanges();
              sel.addRange(this._savedRange);
            }
          }
        },
        insertImageAtCursor(src, alt) {
          this.restoreSelection();
          if (!this.$refs.editor) {
            return;
          }
          var img = document.createElement("img");
          img.src = src;
          if (alt) {
            img.alt = alt;
          }
          img.className = "max-w-full h-auto rounded";
          img.style.maxWidth = "100%";
          img.style.height = "auto";

          var sel = window.getSelection();
          if (sel && sel.rangeCount > 0) {
            var range = sel.getRangeAt(0);
            range.deleteContents();
            range.insertNode(img);
            range.setStartAfter(img);
            range.setEndAfter(img);
            sel.removeAllRanges();
            sel.addRange(range);
          } else {
            this.$refs.editor.appendChild(img);
          }
          this.syncToTextarea();
          this.closeImageModal();
        },
        confirmInsertImage() {
          var fileInput = document.getElementById("compose-image-file-input");
          var urlInput = document.getElementById("compose-image-url-input");
          var self = this;

          if (fileInput && fileInput.files && fileInput.files[0]) {
            var file = fileInput.files[0];
            var reader = new FileReader();
            reader.onload = function (e) {
              var dataUrl = e.target && e.target.result;
              if (typeof dataUrl === "string") {
                self.insertImageAtCursor(dataUrl, file.name);
              }
            };
            reader.readAsDataURL(file);
            return;
          }

          if (urlInput && urlInput.value && urlInput.value.trim().length > 0) {
            var url = urlInput.value.trim();
            this.insertImageAtCursor(url, "");
          }
        },
        onEditorPaste(event) {
          var clipboardData = event.clipboardData || window.clipboardData;
          if (!clipboardData || !clipboardData.items) {
            return;
          }
          for (var i = 0; i < clipboardData.items.length; i += 1) {
            var item = clipboardData.items[i];
            if (item.type && item.type.indexOf("image") !== -1) {
              event.preventDefault();
              var file = item.getAsFile();
              if (file) {
                var self2 = this;
                var reader2 = new FileReader();
                reader2.onload = function (e) {
                  if (e.target && typeof e.target.result === "string") {
                    self2.insertImageAtCursor(e.target.result, "pasted-image");
                  }
                };
                reader2.readAsDataURL(file);
              }
              return;
            }
          }
        }
      };
    });
  });
})();
