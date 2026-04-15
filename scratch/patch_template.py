#!/usr/bin/env python3
"""Patch app_settings.html to add save button loading states and better feedback."""
import sys

path = "/home/vu/toolsauto/app/templates/pages/app_settings.html"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

changes = 0

# 1. Desktop "Luu tat ca" button - add HTMX loading indicators
old_desktop_btn = '''          <button type="submit" form="settings-bulk"
                  class="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all duration-150 shadow-sm hover:shadow-md active:scale-95">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            L\u01b0u t\u1ea5t c\u1ea3
          </button>'''

new_desktop_btn = '''          <button type="submit" form="settings-bulk" id="btn-save-all-desktop"
                  class="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all duration-150 shadow-sm hover:shadow-md active:scale-95 disabled:opacity-60 disabled:cursor-wait">
            <svg class="w-4 h-4 save-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            <svg class="w-4 h-4 save-spinner hidden animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
            <span class="save-label">L\u01b0u t\u1ea5t c\u1ea3</span>
          </button>'''

if old_desktop_btn in text:
    text = text.replace(old_desktop_btn, new_desktop_btn)
    changes += 1
    print("[OK] Updated desktop save button with loading state")
else:
    print("[SKIP] Desktop save button not found")

# 2. Mobile "Luu tat ca" button - add loading indicators
old_mobile_btn = '''          <button type="submit" class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all whitespace-nowrap shadow-sm">L\u01b0u t\u1ea5t c\u1ea3</button>'''

new_mobile_btn = '''          <button type="submit" id="btn-save-all-mobile" class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all whitespace-nowrap shadow-sm disabled:opacity-60 disabled:cursor-wait">
            <svg class="w-4 h-4 save-spinner hidden animate-spin inline-block mr-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
            <span class="save-label">L\u01b0u t\u1ea5t c\u1ea3</span>
          </button>'''

if old_mobile_btn in text:
    text = text.replace(old_mobile_btn, new_mobile_btn)
    changes += 1
    print("[OK] Updated mobile save button with loading state")
else:
    print("[SKIP] Mobile save button not found")

# 3. Add enhanced script at end of script_extra block for loading state management
old_script_end = '''</script>
{% endblock %}'''

new_script_end = '''  // ─── Save Button Loading State ───────────────────────────────────
  (function () {
    var form = document.getElementById('settings-bulk');
    if (!form) return;

    // Before HTMX sends the request: show spinner, disable buttons
    form.addEventListener('htmx:beforeRequest', function () {
      document.querySelectorAll('.save-label').forEach(function (el) {
        el.textContent = '\u0110ang l\u01b0u...';
      });
      document.querySelectorAll('.save-icon').forEach(function (el) {
        el.classList.add('hidden');
      });
      document.querySelectorAll('.save-spinner').forEach(function (el) {
        el.classList.remove('hidden');
      });
      document.querySelectorAll('[type="submit"]').forEach(function (btn) {
        if (btn.form === form || btn.getAttribute('form') === 'settings-bulk') {
          btn.disabled = true;
        }
      });
    });

    // After HTMX completes: restore buttons
    form.addEventListener('htmx:afterRequest', function (evt) {
      document.querySelectorAll('.save-label').forEach(function (el) {
        el.textContent = 'L\u01b0u t\u1ea5t c\u1ea3';
      });
      document.querySelectorAll('.save-icon').forEach(function (el) {
        el.classList.remove('hidden');
      });
      document.querySelectorAll('.save-spinner').forEach(function (el) {
        el.classList.add('hidden');
      });
      document.querySelectorAll('[type="submit"]').forEach(function (btn) {
        if (btn.form === form || btn.getAttribute('form') === 'settings-bulk') {
          btn.disabled = false;
        }
      });
    });
  })();

  // ─── Reset Button Feedback ─────────────────────────────────────────
  document.querySelectorAll('form[id^="reset-form-"]').forEach(function (resetForm) {
    resetForm.addEventListener('htmx:afterRequest', function (evt) {
      // After a successful reset, reload the page to show updated values
      if (evt.detail.successful) {
        setTimeout(function () { window.location.reload(); }, 800);
      }
    });
  });
</script>
{% endblock %}'''

if old_script_end in text:
    text = text.replace(old_script_end, new_script_end, 1)
    changes += 1
    print("[OK] Added loading state management script")
else:
    print("[SKIP] Script end block not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"\nDone. {changes} change(s) applied.")
