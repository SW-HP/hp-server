## commands
1. **Docker 컨테이너 생성**
   ```bash
   sudo docker build -t main .
   sudo docker run -p 8000:8000 --name main -d -v $(pwd):/app \
     --log-driver=json-file \
     --log-opt max-size=10m \
     --log-opt max-file=3 \
     main
   ```

2. 서버 시간 설정
   ```bash
   sudo timedatectl set-timezone Asia/Seoul
   ```
