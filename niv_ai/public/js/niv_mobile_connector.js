// Patch: Add Mobile App section to Connectors tab in Niv Chat Settings
// File: niv_ai/niv_ui/public/js/niv_mobile_connector.js
// This script is loaded after the main niv_settings.js

document.addEventListener('DOMContentLoaded', function() {
    // Observe for the connectors section to appear
    var checkInterval = setInterval(function() {
        var titles = document.querySelectorAll('.ns-section-title');
        for (var i = 0; i < titles.length; i++) {
            if (titles[i].textContent.trim() === 'Connectors') {
                if (!document.getElementById('mobile-pairing-card')) {
                    addMobilePairingCard(titles[i].parentElement);
                }
            }
        }
    }, 2000);

    // Stop checking after 60 seconds
    setTimeout(function() { clearInterval(checkInterval); }, 60000);
});

function addMobilePairingCard(container) {
    if (!container) return;
    var card = document.createElement('div');
    card.id = 'mobile-pairing-card';
    card.className = 'ns-card';
    card.style.cssText = 'margin-top:20px;';
    card.innerHTML = [
        '<div class="ns-card-title-row">',
            '<div>',
                '<div class="ns-card-title">\ud83d\udcf1 Mobile App</div>',
                '<div class="ns-card-desc">Connect Chanakya AI mobile app to your account.</div>',
            '</div>',
        '</div>',
        '<div style="padding:16px 0">',
            '<div id="pairing-result" style="display:none;text-align:center;padding:20px;">',
                '<div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#6b7280;margin-bottom:8px;">Your Pairing Code</div>',
                '<div id="pairing-code" style="font-size:36px;font-weight:800;letter-spacing:6px;color:#7c3aed;font-family:monospace;margin-bottom:12px;"></div>',
                '<div id="pairing-url" style="font-size:12px;color:#6b7280;margin-bottom:4px;"></div>',
                '<div id="pairing-expiry" style="font-size:12px;color:#6b7280;"></div>',
            '</div>',
            '<div style="text-align:center;margin-top:8px;">',
                '<button id="btn-gen-pair" class="ns-btn ns-btn-primary" style="font-size:14px;padding:10px 24px;">',
                    '\ud83d\udd11 Generate Pairing Code',
                '</button>',
            '</div>',
            '<div style="text-align:center;margin-top:16px;font-size:12px;color:#6b7280;line-height:1.8;">',
                '1. Open Chanakya AI app on your phone<br>',
                '2. Enter your server URL and pairing code<br>',
                '3. Start chatting from anywhere!',
            '</div>',
        '</div>'
    ].join('');
    container.appendChild(card);

    document.getElementById('btn-gen-pair').addEventListener('click', function() {
        var btn = this;
        btn.disabled = true;
        btn.textContent = '\u23f3 Generating...';
        frappe.call({
            method: 'niv_ai.niv_core.api.mobile_self_pair.get_my_pairing_code',
            callback: function(r) {
                if (r.message && r.message.success) {
                    document.getElementById('pairing-code').textContent = r.message.code;
                    document.getElementById('pairing-url').textContent = 'Server: ' + r.message.site_url;
                    document.getElementById('pairing-expiry').textContent = 'Expires: ' + r.message.expires_at;
                    document.getElementById('pairing-result').style.display = 'block';
                    btn.textContent = '\ud83d\udd04 Regenerate Code';
                } else {
                    frappe.msgprint('Failed to generate pairing code');
                    btn.textContent = '\ud83d\udd11 Generate Pairing Code';
                }
                btn.disabled = false;
            },
            error: function() {
                frappe.msgprint('Error generating pairing code');
                btn.textContent = '\ud83d\udd11 Generate Pairing Code';
                btn.disabled = false;
            }
        });
    });
}
