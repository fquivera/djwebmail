/* Progressive UI behaviors for the compose editor.
 *
 * Alpine component for recipient toggles (Cc/Bcc), Rich Text / Plain Text
 * toggling, formatting commands via document.execCommand, active button state
 * tracking via document.queryCommandState, and synchronization between
 * contenteditable and the form textarea.
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
        }
      };
    });
  });
})();
