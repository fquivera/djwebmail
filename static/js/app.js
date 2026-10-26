/* Progressive UI behaviors for the mail shell.
 *
 * Alpine components hold only local UI state: the mobile folder drawer and the
 * optimistic read/star controls. Every server mutation still goes through an
 * HTMX request that returns an HTML fragment. Keyboard shortcuts and dialog
 * focus are browser concerns, so they live in plain event listeners.
 *
 * This file must load before alpine-csp.min.js: that bundle starts Alpine in a
 * microtask and emits `alpine:init`, so the component registrations below have
 * to exist first.
 */
(function () {
  "use strict";

  document.documentElement.setAttribute("data-js", "true");

  var loadingTargets = ["message-viewer", "message-list-results"];
  var keyboardNavigation = false;
  var pendingFolderFocus = false;

  function closestDialog(element) {
    return element instanceof Element ? element.closest("dialog") : null;
  }

  function openDialog(dialog) {
    if (!dialog || typeof dialog.showModal !== "function") {
      return;
    }
    document.querySelectorAll("dialog[open]").forEach(function (other) {
      if (other !== dialog) {
        other.close();
      }
    });
    if (!dialog.open) {
      dialog.showModal();
    }
    var autofocus = dialog.querySelector("[data-dialog-autofocus]");
    if (autofocus) {
      window.setTimeout(function () {
        if (!dialog.open) {
          return;
        }
        autofocus.focus();
        if (typeof autofocus.select === "function") {
          autofocus.select();
        }
      }, 0);
    }
  }

  function closeDialog(dialog) {
    if (dialog && dialog.open) {
      dialog.close();
    }
  }

  function isEditable(target) {
    if (!(target instanceof Element)) {
      return false;
    }
    var tag = target.tagName;
    return (
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      target.isContentEditable ||
      target.closest("[contenteditable='true']") !== null
    );
  }

  function focusRow(direction) {
    var rows = Array.prototype.slice.call(
      document.querySelectorAll("[data-mail-row]"),
    );
    if (!rows.length) {
      return false;
    }
    var index = rows.indexOf(document.activeElement);
    if (index === -1) {
      index = direction > 0 ? 0 : rows.length - 1;
    } else {
      index = Math.min(rows.length - 1, Math.max(0, index + direction));
    }
    rows[index].focus();
    rows[index].scrollIntoView({ block: "nearest" });
    return true;
  }

  function syncViewFromUrl() {
    var shell = document.querySelector("[data-mail-shell]");
    if (!shell) {
      return;
    }
    var params = new URLSearchParams(window.location.search);
    shell.setAttribute(
      "data-view",
      params.get("view") === "message" ? "message" : "list",
    );
  }

  function showListView() {
    var shell = document.querySelector("[data-mail-shell]");
    if (!shell) {
      return;
    }
    shell.setAttribute("data-view", "list");
    var url = new URL(window.location.href);
    if (url.searchParams.get("view") === "message") {
      url.searchParams.delete("view");
      window.history.replaceState(window.history.state, "", url.toString());
    }
  }

  function setLoading(target, loading) {
    if (!(target instanceof Element) || loadingTargets.indexOf(target.id) === -1) {
      return;
    }
    target.classList.toggle("is-loading", loading);
    if (loading) {
      target.setAttribute("aria-busy", "true");
    } else {
      target.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("alpine:init", function () {
    if (!window.Alpine) {
      return;
    }

    window.Alpine.data("mailShell", function () {
      return {
        foldersOpen: false,
        openFolders() {
          this.foldersOpen = true;
          window.setTimeout(function () {
            var nav = document.getElementById("folder-tree");
            var first = nav ? nav.querySelector("a, button") : null;
            if (first) {
              first.focus();
            }
          }, 0);
        },
        closeFolders() {
          if (!this.foldersOpen) {
            return;
          }
          this.foldersOpen = false;
          window.setTimeout(function () {
            if (document.querySelector("dialog[open]")) {
              return;
            }
            var toggle = document.querySelector('[aria-controls="folder-tree"]');
            if (toggle) {
              toggle.focus();
            }
          }, 0);
        },
        closeFoldersAfterNavigation() {
          if (this.foldersOpen) {
            pendingFolderFocus = true;
          }
          this.foldersOpen = false;
        },
        toggleFolders() {
          if (this.foldersOpen) {
            this.closeFolders();
          } else {
            this.openFolders();
          }
        },
      };
    });

    window.Alpine.data("messageActions", function () {
      return {
        seen: false,
        flagged: false,
        error: false,
        previousSeen: false,
        busySeen: false,
        busyFlag: false,
        init() {
          this.seen = this.$el.dataset.seen === "true";
          this.flagged = this.$el.dataset.flagged === "true";
        },
        toggleSeen() {
          if (this.busySeen) {
            return;
          }
          this.busySeen = true;
          this.error = false;
          this.seen = !this.seen;
          this.$refs.readAction.value = this.seen ? "read" : "unread";
          this.$refs.readForm.requestSubmit();
        },
        toggleFlag() {
          if (this.busyFlag) {
            return;
          }
          this.busyFlag = true;
          this.error = false;
          this.flagged = !this.flagged;
          this.$refs.flagAction.value = this.flagged ? "star" : "unstar";
          this.$refs.flagForm.requestSubmit();
        },
        afterFlagRequest(event) {
          if (event.target.getAttribute("data-flag-kind") === "seen") {
            this.busySeen = false;
          } else {
            this.busyFlag = false;
          }
          if (event.detail.successful) {
            return;
          }
          this.error = true;
          if (event.target.getAttribute("data-flag-kind") === "seen") {
            this.seen = !this.seen;
          } else {
            this.flagged = !this.flagged;
          }
        },
        onAutoReadStart(event) {
          if (!event.target.hasAttribute("data-auto-read")) {
            return;
          }
          this.previousSeen = this.seen;
          this.busySeen = true;
          this.seen = true;
        },
        onAutoReadEnd(event) {
          if (!event.target.hasAttribute("data-auto-read")) {
            return;
          }
          this.busySeen = false;
          if (!event.detail.successful) {
            this.seen = this.previousSeen;
            this.error = true;
          }
        },
      };
    });
  });

  document.addEventListener("click", function (event) {
    if (!(event.target instanceof Element)) {
      return;
    }

    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      var dialog = document.getElementById(
        opener.getAttribute("data-dialog-open"),
      );
      if (dialog) {
        event.preventDefault();
        openDialog(dialog);
        return;
      }
    }

    var closer = event.target.closest("[data-dialog-close], [data-palette-close]");
    if (closer) {
      if (closer.matches("a[hx-target='#message-viewer']")) {
        keyboardNavigation = true;
      }
      closeDialog(closestDialog(closer));
    }

    var paletteSearch = event.target.closest("[data-palette-search]");
    if (paletteSearch) {
      event.preventDefault();
      var paletteQuery = document.getElementById("palette-query");
      closeDialog(document.getElementById("command-palette"));
      showListView();
      var searchForm = document.getElementById("search-form");
      var search = searchForm
        ? searchForm.querySelector('input[name="q"]')
        : null;
      if (searchForm && search && paletteQuery && paletteQuery.value.trim()) {
        search.value = paletteQuery.value;
        var scope = searchForm.querySelector('select[name="scope"]');
        if (scope && paletteSearch.getAttribute("data-palette-scope")) {
          scope.value = paletteSearch.getAttribute("data-palette-scope");
        }
        searchForm.requestSubmit();
        return;
      }
      if (search) {
        search.focus();
        if (typeof search.select === "function") {
          search.select();
        }
      }
    }
  });

  document.addEventListener("keydown", function (event) {
    var key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    var command = event.ctrlKey || event.metaKey;

    if (command && key === "k") {
      event.preventDefault();
      openDialog(document.getElementById("command-palette"));
      return;
    }

    if (document.querySelector("dialog[open]")) {
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey || isEditable(event.target)) {
      return;
    }

    if (key === "?") {
      event.preventDefault();
      openDialog(document.getElementById("shortcuts-dialog"));
      return;
    }

    if (key === "/") {
      var search = document.querySelector('#search-form input[name="q"]');
      if (search) {
        event.preventDefault();
        showListView();
        search.focus();
        if (typeof search.select === "function") {
          search.select();
        }
      }
      return;
    }

    if (key === "j" || key === "k") {
      showListView();
      if (focusRow(key === "j" ? 1 : -1)) {
        event.preventDefault();
      }
      return;
    }

    if (key === "c") {
      var compose = document.querySelector('[data-shortcut="compose"]');
      if (compose) {
        event.preventDefault();
        compose.click();
      } else {
        var page = document.querySelector("[data-compose-url]");
        var composeUrl = page ? page.getAttribute("data-compose-url") : "";
        if (composeUrl) {
          event.preventDefault();
          window.location.assign(composeUrl);
        }
      }
      return;
    }

    if (key === "r") {
      var reply = document.querySelector('[data-shortcut="reply"]');
      if (reply) {
        event.preventDefault();
        reply.click();
      }
      return;
    }

    if (key === "e") {
      var read = document.querySelector('[data-shortcut="toggle-read"]');
      if (read) {
        event.preventDefault();
        read.click();
      }
      return;
    }

    if (key === "m") {
      var move = document.querySelector('[data-shortcut="move"]');
      if (move) {
        event.preventDefault();
        move.focus();
      }
      return;
    }

    if (key === "u") {
      var back = document.querySelector('[data-shortcut="back"]');
      if (back) {
        event.preventDefault();
        back.click();
      }
    }
  });

  document.addEventListener("htmx:beforeRequest", function (event) {
    setLoading(event.detail.target, true);
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    setLoading(event.detail.target, false);
    if (!event.detail.successful && event.detail.target) {
      if (event.detail.target.id === "message-list") {
        pendingFolderFocus = false;
      }
      if (event.detail.target.id === "message-viewer") {
        keyboardNavigation = false;
      }
    }
  });

  document.addEventListener("htmx:afterSettle", function (event) {
    setLoading(event.detail.target, false);
    syncViewFromUrl();
    var target = event.detail.target;
    if (target && target.id === "message-list" && pendingFolderFocus) {
      pendingFolderFocus = false;
      var folderHeading = document.getElementById("folder-heading");
      if (folderHeading) {
        folderHeading.focus();
      }
    }
    if (target && target.id === "message-viewer") {
      var heading = target.querySelector("#message-subject");
      if (keyboardNavigation && heading) {
        heading.focus();
      }
      keyboardNavigation = false;
    }
  });

  document.addEventListener("htmx:pushedIntoHistory", syncViewFromUrl);
  document.addEventListener("htmx:historyRestore", syncViewFromUrl);
  window.addEventListener("popstate", syncViewFromUrl);

  document.addEventListener("keydown", function (event) {
    if (
      event.key === "Enter" &&
      event.target instanceof Element &&
      event.target.matches("[data-mail-row]")
    ) {
      keyboardNavigation = true;
    }
  });
})();
