#!/bin/bash
# Script khởi động dự án an toàn, chống rớt mạng WSL
# Tự động tạo tmux session và chạy ./start.sh bên trong

cd "$(dirname "$0")" || exit 1

SESSION_NAME="worker_ngam"

# Kiểm tra xem session tmux "worker_ngam" đã tồn tại chưa
tmux has-session -t $SESSION_NAME 2>/dev/null

if [ $? != 0 ]; then
  echo "🚀 Bắt đầu tạo không gian chạy ngầm..."
  
  # Tạo session tmux mới và chạy ngầm (detached)
  tmux new-session -d -s $SESSION_NAME
  
  # Gửi lệnh bật toàn bộ web & worker của anh vào trong đó
  tmux send-keys -t $SESSION_NAME "./start.sh" C-m
  
  echo -e "\033[0;32m✅ Đã khởi động dự án chạy ngầm thành công bằng tmux!\033[0m"
else
  echo -e "\033[1;33m⚠️ Không gian chạy ngầm vẫn đang hoạt động từ trước.\033[0m"
  echo "Lệnh ./start.sh có thể đã được chạy. Anh cứ chui vào xem nếu cần nhé."
fi

echo "========================================================="
echo "👉 Lệnh 1: XEM màn hình đang chạy ngầm:"
echo "           tmux attach -t $SESSION_NAME"
echo "           (Xem xong bấm Ctrl + B rồi D để thoát ra, không tắt VSCode ngang)"
echo ""
echo "👉 Lệnh 2: TẮT sạch sẽ tiến trình nếu bị lỗi/kẹt:"
echo "           ./stop_tmux.sh"
echo "========================================================="
