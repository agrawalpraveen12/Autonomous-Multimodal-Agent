const chatArea = document.getElementById('chat-area');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const fileUpload = document.getElementById('file-upload');
const attachmentPreview = document.getElementById('attachment-preview');

let currentFile = null;
const API_URL = window.location.origin + "/api";

function addMessage(content, isUser = false) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', isUser ? 'user-message' : 'bot-message');

    const contentDiv = document.createElement('div');
    contentDiv.classList.add('message-content');

    if (isUser) {
        contentDiv.textContent = content;
    } else {
        contentDiv.innerHTML = marked.parse(content);
    }

    msgDiv.appendChild(contentDiv);
    chatArea.appendChild(msgDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
}

async function handleSendMessage() {
    const text = userInput.value.trim();
    if (!text && !currentFile) return;

    let displayMsg = text;
    if (currentFile) {
        displayMsg = (text ? text + "\n" : "") + `[Attached: ${currentFile.name}]`;
    }
    addMessage(displayMsg, true);

    userInput.value = '';
    const tempFile = currentFile;
    currentFile = null;
    attachmentPreview.style.display = 'none';
    attachmentPreview.textContent = '';

    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.classList.add('message', 'bot-message');
    loadingDiv.innerHTML = '<div class="message-content">Thinking...</div>';
    chatArea.appendChild(loadingDiv);
    chatArea.scrollTop = chatArea.scrollHeight;

    try {
        let uploadedFilePath = null;

        if (tempFile) {
            const formData = new FormData();
            formData.append('file', tempFile);

            const uploadResp = await fetch(`${API_URL}/upload`, {
                method: 'POST',
                body: formData
            });

            const uploadResult = await uploadResp.json();
            uploadedFilePath = uploadResult.filepath;
        }

        const payload = {
            message: text,
            file_path: uploadedFilePath
        };

        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        document.getElementById(loadingId).remove();

        if (data.response) {
            addMessage(data.response);

            if (data.extracted_content) {
                const details = document.createElement('details');
                details.innerHTML = `
                    <summary>View Extracted Content</summary>
                    <pre style="white-space: pre-wrap;">${data.extracted_content}</pre>`;
                chatArea.lastElementChild.querySelector('.message-content').appendChild(details);
            }
        }

    } catch (error) {
        document.getElementById(loadingId).remove();
        addMessage(`Error: ${error.message}`);
    }
}

fileUpload.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        currentFile = e.target.files[0];
        attachmentPreview.textContent = `Attached: ${currentFile.name}`;
        attachmentPreview.style.display = 'block';
    }
});

sendBtn.addEventListener('click', handleSendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSendMessage();
});
