# Python 가상환경 설정 및 실행 방법

이 문서는 **Bash** 및 **CMD** 환경에서 Python 기본 가상환경을 설정하고 실행하는 방법을 설명합니다.

---

## **필수 조건**

1. Python이 시스템에 설치되어 있어야 합니다. *(개발 당시 3.11.8 버전 사용)*
2. 사용 중인 터미널이 **Bash**(예: Linux, macOS, 또는 Windows의 Git Bash) 또는 **CMD**(Windows 명령 프롬프트)인지 확인하세요.
3. 명령 실행 전에 프로젝트 디렉토리로 이동하세요:

# 가상환경 생성 및 활성화
가상환경을 생성하고 활성화하려면 아래 명령어를 사용하세요.

## Bash
   ```bash
   python3 -m venv capstone
   source capstone/bin/activate
   ```

## CMD
   ```cmd
   python -m venv capstone
   capstone\Scripts\activate
   ```

---

# Uvicorn 실행
가상환경이 활성화된 상태에서 아래 명령어를 사용하세요.

## command
   ```cmd
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

---