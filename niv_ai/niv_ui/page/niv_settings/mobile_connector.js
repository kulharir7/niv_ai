/**
 * Inject "Mobile App" section into Niv Chat Settings → Connectors tab
 * This runs as a Client Script on "Web Page" or via custom_app.js
 * Add as: Website Script (or inject via hooks)
 */
(function() {
    // Wait for Niv Settings page to load
    var observer = new MutationObserver(function(mutations) {
        var connectors = document.querySelector('.ns-section-title');
        if (connectors && connectors.textContent === 'Connectors') {
            // Check if already injected
            if (document.querySelector('#mobile-pairing-card')) return;
            injectMobilePairingCard();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    function injectMobilePairingCard() {
        var container = document.querySelector('.ns-section-title');
        if (!container) return;
        
        // Find the parent content area
        var content = container.parentElement;
        if (!content) return;

        var card = document.createElement('div');
        card.id = 'mobile-pairing-card';
        card.className = 'ns-card';
        card.style.marginTop = '20px';
        card.innerHTML = 
            '<div class="ns-card-title-row">' +
                '<div>' +
                    '<div class="ns-card-title">📱 Mobile App</div>' +
                    '<div class="ns-card-desc">Connect Chanakya AI mobile app to your account.</div>' +
                '</div>' +
            '</div>' +
            '<div style="padding:16px 0">' +
                '<div id="pairing-result" style="display:none; text-align:center; padding:20px;">' +
                    '<div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#6b7280; margin-bottom:8px;">Your Pairing Code</div>' +
                    '<div id="pairing-code" style="font-size:36px; font-weight:800; letter-spacing:6px; color:#7c3aed; font-family:monospace; margin-bottom:12px;"></div>' +
                    '<div id="pairing-url" style="font-size:12px; color:#6b7280; margin-bottom:4px;"></div>' +
                    '<div id="pairing-expiry" style="font-size:12px; color:#6b7280;"></div>' +
                '</div>' +
                '<div style="text-align:center; margin-top:8px;">' +
                    '<button id="btn-generate-pairing" class="ns-btn ns-btn-primary" style="font-size:14px; padding:10px 24px;">' +
                        '🔑 Generate Pairing Code' +
                    '</button>' +
                '</div>' +
                '<div style="text-align:center; margin-top:16px; font-size:12px; color:#6b7280;">' +
                    '1. Open Chanakya AI app on your phone<br>' +
                    '2. Enter the pairing code shown above<br>' +
                    '3. Start chatting from anywhere!' +
                '</div>' +
            '</div>';

        content.appendChild(card);

        // Button click handler
        document.getElementById('btn-generate-pairing').addEventListener('click', function() {
            var btn = this;
            btn.disabled = true;
            btn.textContent = '⏳ Generating...';

            frappe.call({
                method: 'niv_ai.niv_core.api.mobile_self_pair.get_my_pairing_code',
                callback: function(r) {
                    if (r.message && r.message.success) {
                        document.getElementById('pairing-code').textContent = r.message.code;
                        document.getElementById('pairing-url').textContent = 'Server: ' + r.message.site_url;
                        document.getElementById('pairing-expiry').textContent = 'Expires: ' + r.message.expires_at;
                        document.getElementById('pairing-result').style.display = 'block';
                        btn.textContent = '🔄 Regenerate Code';
                        btn.disabled = false;
                    } else {
                        frappe.msgprint('Failed to generate pairing code');
                        btn.textContent = '🔑 Generate Pairing Code';
                        btn.disabled = false;
                    }
                },
                error: function() {
                    frappe.msgprint('Error generating pairing code');
                    btn.textContent = '🔑 Generate Pairing Code';
                    btn.disabled = false;
                }
            });
        });
    }
})();
