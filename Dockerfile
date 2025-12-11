# Sử dụng Python phiên bản nhẹ (slim) để build nhanh
FROM python:3.10-slim

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Copy file requirements.txt vào trước để cài thư viện
COPY requirements.txt .

# Cài đặt các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code còn lại vào container
COPY . .

# Mở port 8080 (Trùng với port trong file keep_alive.py)
EXPOSE 8080

# Lệnh chạy bot khi container khởi động
CMD ["python", "main.py"]
