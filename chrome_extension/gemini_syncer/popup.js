document.addEventListener('DOMContentLoaded', () => {
    const vpsUrlInput = document.getElementById('vps_url');
    const apiSecretInput = document.getElementById('api_secret');
    const syncBtn = document.getElementById('sync_btn');
    const statusDiv = document.getElementById('status');

    // Load saved settings
    chrome.storage.local.get(['vpsUrl', 'apiSecret'], (result) => {
        if (result.vpsUrl) vpsUrlInput.value = result.vpsUrl;
        if (result.apiSecret) apiSecretInput.value = result.apiSecret;
    });

    function showStatus(message, className) {
        statusDiv.textContent = message;
        statusDiv.className = className;
    }

    syncBtn.addEventListener('click', async () => {
        const vpsUrlOrig = vpsUrlInput.value.trim();
        const apiSecret = apiSecretInput.value.trim();

        if (!vpsUrlOrig || !apiSecret) {
            showStatus('Vui lòng nhập IP VPS và Mã Bảo Mật', 'error');
            return;
        }

        // Auto append /health/gemini/cookie-sync
        let vpsUrl = vpsUrlOrig;
        if (!vpsUrl.endsWith('/health/gemini/cookie-sync')) {
            vpsUrl = vpsUrl.replace(/\/$/, '') + '/health/gemini/cookie-sync';
        }

        // Save settings for next time
        chrome.storage.local.set({ vpsUrl: vpsUrlOrig, apiSecret });

        syncBtn.disabled = true;
        showStatus('Đang trích xuất cookie từ Google...', '');

        try {
            // Get all cookies from google.com
            const cookies = await chrome.cookies.getAll({ domain: '.google.com' });

            if (!cookies || cookies.length === 0) {
                showStatus('Không tìm thấy cookie! Bạn phải đăng nhập Gemini trên tab này trước.', 'error');
                syncBtn.disabled = false;
                return;
            }

            // Convert Chrome cookie format into undetected_chromedriver compatible JSON format
            const exportCookies = cookies.map(c => ({
                domain: c.domain,
                name: c.name,
                value: c.value,
                path: c.path,
                expiry: c.expirationDate ? Math.floor(c.expirationDate) : Math.floor(Date.now() / 1000 + 31536000),
                httpOnly: c.httpOnly,
                secure: c.secure
            }));

            showStatus(`Bắt được ${exportCookies.length} cookies. Đang truyền lên VPS...`, '');

            const response = await fetch(vpsUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-secret': apiSecret
                },
                body: JSON.stringify(exportCookies)
            });

            if (response.ok) {
                const data = await response.json();
                showStatus('✅ Bơm Cookie thành công! VPS đã hồi sinh.', 'success');
            } else {
                let errorText = "";
                try {
                    const errObj = await response.json();
                    errorText = errObj.detail || JSON.stringify(errObj);
                } catch (e) {
                    errorText = await response.text();
                }
                showStatus(`❌ Lỗi VPS: ${response.status} - ${errorText}`, 'error');
            }
        } catch (error) {
            showStatus(`❌ Lỗi kết nối (Sai IP/Port hoặc máy chủ sập): ${error.message}`, 'error');
        } finally {
            syncBtn.disabled = false;
        }
    });
});
