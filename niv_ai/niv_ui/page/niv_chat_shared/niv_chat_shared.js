frappe.pages["niv-chat-shared"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Shared Chat",
        single_column: true,
    });

    $(wrapper).find(".page-head").hide();

    // Load marked.js
    const loadScript = (src) => new Promise((resolve) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        document.head.appendChild(s);
    });

    const deps = [];
    if (!window.marked) {
        deps.push(loadScript("https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"));
    }

    Promise.all(deps).then(() => {
        if (window.marked) {
            marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
        }
        load_shared_chat(page);
    });
};

function load_shared_chat(page) {
    const $body = $(page.body);
    $body.html(frappe.render_template("niv_chat_shared"));

    // Extract hash from URL: /app/niv-chat-shared/<hash>
    const path = window.location.pathname;
    const parts = path.split("/");
    const hash = parts[parts.length - 1];

    if (!hash || hash === "niv-chat-shared") {
        $body.find(".niv-shared-messages").html(
            '<div class="niv-shared-expired">No shared chat specified.</div>'
        );
        return;
    }

    frappe.call({
        method: "niv_ai.niv_core.api.conversation.get_shared_messages",
        args: { share_hash: hash },
        callback: (r) => {
            const data = r.message;
            if (!data) {
                $body.find(".niv-shared-messages").html(
                    '<div class="niv-shared-expired">This shared chat is no longer available.</div>'
                );
                return;
            }

            $body.find(".shared-title").text(data.title || "Shared Chat");
            const $messages = $body.find(".niv-shared-messages");

            for (const msg of data.messages) {
                if (msg.role === "system" || msg.role === "tool") continue;
                const isUser = msg.role === "user";
                const avatar = isUser ? "U" : "N";
                const content = window.marked ? marked.parse(msg.content || "") : frappe.utils.escape_html(msg.content || "");
                const time = msg.creation ? frappe.datetime.prettyDate(msg.creation) : "";

                $messages.append(`
                    <div class="shared-message ${msg.role}">
                        <div class="shared-msg-avatar">${avatar}</div>
                        <div class="shared-msg-body">
                            <div class="shared-msg-content">${content}</div>
                            <div class="shared-msg-time">${time}</div>
                        </div>
                    </div>
                `);
            }
        },
        error: () => {
            $body.find(".niv-shared-messages").html(
                '<div class="niv-shared-expired">This shared chat is no longer available or has expired.</div>'
            );
        },
    });
}
