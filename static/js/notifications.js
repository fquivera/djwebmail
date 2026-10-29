/**
 * Desktop Web Notifications and Web Audio API Chime for DjWebmail.
 *
 * Implements:
 * 1. Synthesized 2-tone harmonic chime via Web Audio API (zero external assets/network requests).
 * 2. Native OS desktop alerts via Web Notifications API with click-to-focus.
 * 3. Reactive event listeners for "mail:new-message" and "mail:preference-changed".
 * 4. Settings view permission management and live interactive testing.
 */
(function () {
  "use strict";

  var audioCtx = null;

  function getAudioContext() {
    if (!audioCtx && (window.AudioContext || window.webkitAudioContext)) {
      var AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass();
    }
    return audioCtx;
  }

  function unlockAudio() {
    var ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(function () {});
    }
  }

  window.addEventListener("click", unlockAudio, { once: true, passive: true });
  window.addEventListener("keydown", unlockAudio, { once: true, passive: true });

  function playNotificationChime() {
    try {
      var ctx = getAudioContext();
      if (!ctx) {
        return;
      }
      if (ctx.state === "suspended") {
        ctx.resume();
      }

      var now = ctx.currentTime;

      // Note 1: 587.33 Hz (D5) - Soft introductory chime
      var osc1 = ctx.createOscillator();
      var gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now);
      gain1.gain.setValueAtTime(0, now);
      gain1.gain.linearRampToValueAtTime(0.18, now + 0.02);
      gain1.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      // Note 2: 880.00 Hz (A5) - Clear, pleasant melodic resolution
      var osc2 = ctx.createOscillator();
      var gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(880.00, now + 0.1);
      gain2.gain.setValueAtTime(0, now + 0.1);
      gain2.gain.linearRampToValueAtTime(0.22, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.0001, now + 0.65);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.1);
      osc2.stop(now + 0.65);
    } catch (e) {
      // Audio playback silently suppressed if browser blocks
    }
  }

  function getFaviconUrl() {
    var iconEl = document.querySelector('link[rel="icon"]');
    return iconEl ? iconEl.href : "";
  }

  function showDesktopNotification(title, body, targetUrl, tag) {
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return;
    }

    try {
      var options = {
        body: body || "",
        icon: getFaviconUrl(),
        tag: tag || "djwebmail-notification",
      };
      var notification = new Notification(title || "DjWebmail", options);

      notification.onclick = function () {
        window.focus();
        if (targetUrl) {
          window.location.href = targetUrl;
        }
        notification.close();
      };
    } catch (e) {
      // Fallback or ignore if background notification fails
    }
  }

  function getNotificationsConfig() {
    var body = document.body;
    var notifyEnabled = body.getAttribute("data-notifications-enabled") !== "false";
    var soundEnabled = body.getAttribute("data-notification-sound-enabled") !== "false";
    return {
      notifications: notifyEnabled,
      sound: soundEnabled,
    };
  }

  // Handle incoming mail event
  document.body.addEventListener("mail:new-message", function (event) {
    var detail = event.detail || {};
    var config = getNotificationsConfig();

    var shouldPlaySound = detail.sound !== false && config.sound;
    var shouldNotify = detail.notify !== false && config.notifications;

    if (shouldPlaySound) {
      playNotificationChime();
    }

    if (shouldNotify) {
      var sender = detail.sender || "DjWebmail";
      var subject = detail.subject || "";
      var targetUrl = detail.url || "";
      var tag = "mail-" + (detail.uid || Date.now());
      showDesktopNotification(sender, subject, targetUrl, tag);
    }
  });

  // Handle preferences update event
  document.body.addEventListener("mail:preference-changed", function (event) {
    var detail = event.detail || {};
    if (detail.notifications_enabled !== undefined) {
      document.body.setAttribute(
        "data-notifications-enabled",
        detail.notifications_enabled ? "true" : "false"
      );
    }
    if (detail.notification_sound_enabled !== undefined) {
      document.body.setAttribute(
        "data-notification-sound-enabled",
        detail.notification_sound_enabled ? "true" : "false"
      );
    }
  });

  // Settings page UI helpers
  function updatePermissionUI() {
    var statusEl = document.getElementById("notification-perm-status");
    var reqBtn = document.getElementById("btn-request-notification-perm");
    if (!statusEl) {
      return;
    }

    if (!("Notification" in window)) {
      statusEl.textContent = "✕ Este navegador no soporta notificaciones de escritorio.";
      statusEl.className = "text-xs text-error font-medium";
      if (reqBtn) reqBtn.disabled = true;
      return;
    }

    if (Notification.permission === "granted") {
      statusEl.textContent = "✓ Notificaciones de escritorio permitidas en este navegador.";
      statusEl.className = "text-xs text-success font-medium";
      if (reqBtn) reqBtn.classList.add("hidden");
    } else if (Notification.permission === "denied") {
      statusEl.textContent = "✕ Notificaciones bloqueadas en la configuración del navegador.";
      statusEl.className = "text-xs text-error font-medium";
      if (reqBtn) reqBtn.disabled = true;
    } else {
      statusEl.textContent = "○ Permiso del navegador no solicitado todavía.";
      statusEl.className = "text-xs text-base-content/60";
      if (reqBtn) reqBtn.classList.remove("hidden");
    }
  }

  function initSettingsControls() {
    updatePermissionUI();

    var reqBtn = document.getElementById("btn-request-notification-perm");
    if (reqBtn) {
      reqBtn.onclick = function () {
        if (!("Notification" in window)) return;
        Notification.requestPermission().then(function () {
          updatePermissionUI();
        });
      };
    }

    var testSoundBtn = document.getElementById("btn-test-sound");
    if (testSoundBtn) {
      testSoundBtn.onclick = function () {
        playNotificationChime();
      };
    }

    var testNotifyBtn = document.getElementById("btn-test-notification");
    if (testNotifyBtn) {
      testNotifyBtn.onclick = function () {
        if (!("Notification" in window)) {
          alert("Este navegador no soporta notificaciones de escritorio.");
          return;
        }

        if (Notification.permission === "granted") {
          showDesktopNotification(
            "DjWebmail",
            "Esta es una notificación de prueba de nuevo correo.",
            "",
            "test-notification"
          );
        } else if (Notification.permission === "denied") {
          alert(
            "Las notificaciones están bloqueadas en la configuración de tu navegador. Debes permitirlas en el icono del candado en la barra de direcciones."
          );
        } else {
          Notification.requestPermission().then(function (perm) {
            updatePermissionUI();
            if (perm === "granted") {
              showDesktopNotification(
                "DjWebmail",
                "Esta es una notificación de prueba de nuevo correo.",
                "",
                "test-notification"
              );
            }
          });
        }
      };
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSettingsControls);
  } else {
    initSettingsControls();
  }

  document.addEventListener("htmx:afterSettle", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "settings-form") {
      initSettingsControls();
    }
  });

  // Expose API globally for direct calls or debugging
  window.DjWebmailNotifications = {
    playChime: playNotificationChime,
    show: showDesktopNotification,
  };
})();
