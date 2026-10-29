/**
 * Carbonio-inspired Sieve filter manager interactions.
 * Fully compliant with CSP: zero inline JS/styles, event delegation.
 */
(function () {
  "use strict";

  var selectedRuleId = null;
  var selectedRuleColumn = null;

  function updateButtonStates() {
    var addBtn = document.getElementById("btn-filter-add");
    var removeBtn = document.getElementById("btn-filter-remove");
    var editBtn = document.getElementById("btn-filter-edit");
    var deleteBtn = document.getElementById("btn-filter-delete");

    if (!selectedRuleId) {
      if (addBtn) addBtn.disabled = true;
      if (removeBtn) removeBtn.disabled = true;
      if (editBtn) editBtn.disabled = true;
      if (deleteBtn) deleteBtn.disabled = true;
      return;
    }

    if (editBtn) editBtn.disabled = false;
    if (deleteBtn) deleteBtn.disabled = false;

    if (selectedRuleColumn === "active") {
      if (addBtn) addBtn.disabled = true;
      if (removeBtn) removeBtn.disabled = false;
    } else {
      if (addBtn) addBtn.disabled = false;
      if (removeBtn) removeBtn.disabled = true;
    }
  }

  function clearSelection() {
    selectedRuleId = null;
    selectedRuleColumn = null;
    var allItems = document.querySelectorAll(".filter-item");
    allItems.forEach(function (el) {
      el.classList.remove("bg-primary/10", "border-primary", "text-primary");
      el.classList.add("border-transparent");
    });
    updateButtonStates();
  }

  function openModal(ruleId) {
    var panel = document.getElementById("filters-panel");
    if (!panel) return;

    var activeTab = "incoming";
    var tabBtn = panel.querySelector(".tab-active");
    if (tabBtn && tabBtn.getAttribute("hx-get") && tabBtn.getAttribute("hx-get").indexOf("outgoing") !== -1) {
      activeTab = "outgoing";
    }

    var url = "/mail/filters/modal/?tab=" + encodeURIComponent(activeTab);
    if (ruleId) {
      url += "&rule_id=" + encodeURIComponent(ruleId);
    }

    if (window.htmx) {
      window.htmx.ajax("GET", url, {
        target: "#filter-modal-container",
        swap: "innerHTML",
      });
    }
  }

  function dispatchAction(actionName) {
    var form = document.getElementById("filters-action-form");
    var actionInput = document.getElementById("filter-action-type");
    var ruleInput = document.getElementById("filter-selected-rule-id");
    if (!form || !actionInput || !ruleInput) return;

    actionInput.value = actionName;
    ruleInput.value = selectedRuleId || "";

    if (window.htmx) {
      window.htmx.trigger(form, "submit");
    } else {
      form.submit();
    }
  }

  function closeModal() {
    var modal = document.getElementById("filter-modal");
    if (modal) {
      modal.close();
      modal.remove();
    }
  }

  // Sync action argument hidden input
  function syncActionRow(row) {
    if (!row) return;
    var typeSelect = row.querySelector("[data-action-type-select]");
    var folderSelect = row.querySelector("[data-arg-folder]");
    var emailInput = row.querySelector("[data-arg-email]");
    var hiddenVal = row.querySelector("[data-arg-value]");
    if (!typeSelect || !hiddenVal) return;

    var act = typeSelect.value;
    if (act === "fileinto") {
      if (folderSelect) {
        folderSelect.classList.remove("hidden");
        hiddenVal.value = folderSelect.value;
      }
      if (emailInput) emailInput.classList.add("hidden");
    } else if (act === "redirect") {
      if (emailInput) {
        emailInput.classList.remove("hidden");
        hiddenVal.value = emailInput.value.trim();
      }
      if (folderSelect) folderSelect.classList.add("hidden");
    } else {
      if (folderSelect) folderSelect.classList.add("hidden");
      if (emailInput) emailInput.classList.add("hidden");
      hiddenVal.value = "";
    }
  }

  // Global click delegator
  document.addEventListener("click", function (event) {
    // 1. Filter item selection
    var item = event.target.closest(".filter-item");
    if (item) {
      var itemCol = item.getAttribute("data-rule-column");
      var itemId = item.getAttribute("data-rule-id");

      document.querySelectorAll(".filter-item").forEach(function (el) {
        el.classList.remove("bg-primary/10", "border-primary", "text-primary");
        el.classList.add("border-transparent");
      });

      item.classList.add("bg-primary/10", "border-primary", "text-primary");
      item.classList.remove("border-transparent");

      selectedRuleId = itemId;
      selectedRuleColumn = itemCol;
      updateButtonStates();
      return;
    }

    // 2. Action buttons
    var btn = event.target.closest("[data-action-btn]");
    if (btn) {
      var act = btn.getAttribute("data-action-btn");
      if (act === "create") {
        openModal(null);
      } else if (act === "edit" && selectedRuleId) {
        openModal(selectedRuleId);
      } else if (act === "add" && selectedRuleId) {
        dispatchAction("add");
      } else if (act === "remove" && selectedRuleId) {
        dispatchAction("remove");
      } else if (act === "delete" && selectedRuleId) {
        dispatchAction("delete");
      } else if (act === "apply") {
        dispatchAction("apply");
      }
      return;
    }

    // 3. Modal close
    if (event.target.closest("[data-filter-modal-close]")) {
      closeModal();
      return;
    }

    // 4. Dynamic Condition row: Add
    if (event.target.closest("[data-add-condition]")) {
      var tplCond = document.getElementById("tpl-condition-row");
      var listCond = document.getElementById("filter-conditions-list");
      if (tplCond && listCond) {
        var clone = tplCond.content.cloneNode(true);
        listCond.appendChild(clone);
      }
      return;
    }

    // 5. Dynamic Condition row: Remove
    var rmCond = event.target.closest("[data-remove-condition]");
    if (rmCond) {
      var condRows = document.querySelectorAll("#filter-conditions-list .condition-row");
      if (condRows.length > 1) {
        var row = rmCond.closest(".condition-row");
        if (row) row.remove();
      }
      return;
    }

    // 6. Dynamic Action row: Add
    if (event.target.closest("[data-add-action]")) {
      var tplAct = document.getElementById("tpl-action-row");
      var listAct = document.getElementById("filter-actions-list");
      if (tplAct && listAct) {
        var actClone = tplAct.content.cloneNode(true);
        listAct.appendChild(actClone);
        var newlyAdded = listAct.lastElementChild;
        syncActionRow(newlyAdded);
      }
      return;
    }

    // 7. Dynamic Action row: Remove
    var rmAct = event.target.closest("[data-remove-action]");
    if (rmAct) {
      var actRows = document.querySelectorAll("#filter-actions-list .action-row");
      if (actRows.length > 1) {
        var aRow = rmAct.closest(".action-row");
        if (aRow) aRow.remove();
      }
      return;
    }
  });

  // Double click on filter item to edit
  document.addEventListener("dblclick", function (event) {
    var item = event.target.closest(".filter-item");
    if (item) {
      var itemId = item.getAttribute("data-rule-id");
      if (itemId) {
        openModal(itemId);
      }
    }
  });

  // Action type or argument change
  document.addEventListener("change", function (event) {
    var select = event.target.closest("[data-action-type-select]");
    if (select) {
      syncActionRow(select.closest(".action-row"));
      return;
    }

    var folder = event.target.closest("[data-arg-folder]");
    if (folder) {
      var rowF = folder.closest(".action-row");
      var hiddenF = rowF ? rowF.querySelector("[data-arg-value]") : null;
      if (hiddenF) hiddenF.value = folder.value;
      return;
    }
  });

  document.addEventListener("input", function (event) {
    var email = event.target.closest("[data-arg-email]");
    if (email) {
      var rowE = email.closest(".action-row");
      var hiddenE = rowE ? rowE.querySelector("[data-arg-value]") : null;
      if (hiddenE) hiddenE.value = email.value.trim();
    }
  });

  // When rule is saved, close modal and clear selection
  document.addEventListener("mail:filter-saved", function () {
    closeModal();
    clearSelection();
  });

  // After HTMX swaps into #filters-panel, clear previous selection state
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "filters-panel") {
      clearSelection();
    }
    if (event.detail && event.detail.target && event.detail.target.id === "filter-modal-container") {
      var modal = document.getElementById("filter-modal");
      if (modal && typeof modal.showModal === "function") {
        modal.showModal();
        document.querySelectorAll("#filter-actions-list .action-row").forEach(syncActionRow);
      }
    }
  });
})();
