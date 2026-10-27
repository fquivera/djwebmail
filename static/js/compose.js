/* Progressive UI behaviors for the compose editor.
 *
 * Alpine component for recipient toggles (Cc/Bcc), interactive contact picker
 * and autocomplete, Rich Text / Plain Text toggling, formatting commands via
 * document.execCommand, active button state tracking via
 * document.queryCommandState, and synchronization between contenteditable and
 * the form textarea.
 */
(function () {
  "use strict";

  document.addEventListener("alpine:init", function () {
    if (!window.Alpine) {
      return;
    }

    window.Alpine.data("composer", function () {
      return {
        showCc: false,
        showBcc: false,
        showContacts: false,
        noMatchingContacts: false,
        activeRecipient: "to",
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
        activeRecipientInput() {
          if (this.activeRecipient === "cc" && this.$refs.ccInput) {
            return this.$refs.ccInput;
          }
          if (this.activeRecipient === "bcc" && this.$refs.bccInput) {
            return this.$refs.bccInput;
          }
          return this.$refs.toInput || null;
        },
        focusTo() {
          this.activeRecipient = "to";
          this.openContactsForInput(this.$refs.toInput);
        },
        focusCc() {
          this.activeRecipient = "cc";
          this.openContactsForInput(this.$refs.ccInput);
        },
        focusBcc() {
          this.activeRecipient = "bcc";
          this.openContactsForInput(this.$refs.bccInput);
        },
        inputTo() {
          this.activeRecipient = "to";
          this.filterContactsByInput(this.$refs.toInput);
        },
        inputCc() {
          this.activeRecipient = "cc";
          this.filterContactsByInput(this.$refs.ccInput);
        },
        inputBcc() {
          this.activeRecipient = "bcc";
          this.filterContactsByInput(this.$refs.bccInput);
        },
        openContactsForInput(inputEl) {
          if (!this.$refs.contactsList || !inputEl) {
            return;
          }
          var raw = (inputEl.value || "").trim();
          if (!raw || raw.endsWith(",")) {
            this.filterContactItems("");
            this.showContacts = true;
          }
        },
        filterContactsByInput(inputEl) {
          if (!this.$refs.contactsList || !inputEl) {
            return;
          }
          var parts = (inputEl.value || "").split(",");
          var lastToken = (parts[parts.length - 1] || "").trim().toLowerCase();
          this.filterContactItems(lastToken);
          this.showContacts = true;
        },
        filterContactItems(query) {
          if (!this.$refs.contactsList) {
            return;
          }
          var items = this.$refs.contactsList.querySelectorAll("[data-contact-item]");
          var visibleCount = 0;
          var needle = (query || "").trim().toLowerCase();
          for (var i = 0; i < items.length; i += 1) {
            var item = items[i];
            var haystack = (item.getAttribute("data-search") || "").toLowerCase();
            var matches = !needle || haystack.indexOf(needle) !== -1;
            if (matches) {
              item.classList.remove("hidden");
              visibleCount += 1;
            } else {
              item.classList.add("hidden");
            }
          }
          this.noMatchingContacts = visibleCount === 0;
        },
        toggleContactsPicker() {
          if (!this.$refs.contactsList) {
            return;
          }
          this.showContacts = !this.showContacts;
          if (this.showContacts) {
            this.filterContactItems("");
            var inputEl = this.activeRecipientInput();
            if (inputEl) {
              inputEl.focus();
            }
          }
        },
        closeContacts() {
          this.showContacts = false;
        },
        selectContact(event) {
          var button = event && event.currentTarget ? event.currentTarget : null;
          if (!button) {
            return;
          }
          var address = (button.getAttribute("data-address") || "").trim();
          if (!address) {
            return;
          }
          var inputEl = this.activeRecipientInput();
          if (!inputEl) {
            return;
          }
          var current = inputEl.value || "";
          var rawSegments = current.split(",");
          var kept = [];
          for (var i = 0; i < rawSegments.length - 1; i += 1) {
            var seg = rawSegments[i].trim();
            if (seg && kept.indexOf(seg) === -1) {
              kept.push(seg);
            }
          }
          var lastSeg = (rawSegments[rawSegments.length - 1] || "").trim();
          if (lastSeg && lastSeg.indexOf("@") !== -1 && kept.indexOf(lastSeg) === -1) {
            kept.push(lastSeg);
          }
          if (kept.indexOf(address) === -1) {
            kept.push(address);
          }
          inputEl.value = kept.join(", ");
          this.showContacts = false;
          inputEl.dispatchEvent(new Event("input", { bubbles: true }));
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
          this.closeContacts();
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
          this.closeContacts();
          this.updateFormatState();
          this.syncToTextarea();
        },
        onEditorActivity() {
          this.closeContacts();
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
        }
      };
    });
  });
})();
