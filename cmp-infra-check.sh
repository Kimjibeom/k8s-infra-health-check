#!/bin/bash
#
# CMP 인프라 정기점검 스크립트
# OS, Kubernetes, K8s 서비스, CI/CD, DB 점검 및 보고서 생성
#

set -e

# 스크립트 경로 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/scripts/main.py" 
INVENTORY_FILE="${SCRIPT_DIR}/config/gpu-inventory.yaml"
CHECKS_FILE="${SCRIPT_DIR}/config/check_items.yaml"
OUTPUT_DIR="${SCRIPT_DIR}/output"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 글로벌 변수로 사용할 파이썬 경로 초기화
PYTHON_EXE="python3"

# 의존성 확인 로직 (다양한 Python 버전 대응)
check_dependencies () {
    log_info "의존성 확인 중..."
    
    # 1. 사용 가능한 Python 실행 파일 찾기 (최신 버전 우선 탐색)
    PYTHON_EXE=""
    for cmd in python3.11 python3.10 python3.9 python3; do
        if command -v "$cmd" &> /dev/null; then
            PYTHON_EXE=$(command -v "$cmd")
            break
        fi
    done

    if [ -z "$PYTHON_EXE" ]; then
        log_error "Python3 (3.9 이상 권장) 이 설치되어 있지 않습니다."
        exit 1
    fi

    log_info "사용 중인 Python: $($PYTHON_EXE --version) ($PYTHON_EXE)"

    # 2. 패키지명과 import명이 다른 경우 매핑 처리
    declare -A package_map
    package_map["pyyaml"]="yaml"
    package_map["python-docx"]="docx"

    # 3. 패키지 확인 및 설치
    for pkg in "${!package_map[@]}"; do
        module_name="${package_map[$pkg]}"
        
        # 찾은 실행 파일 ($PYTHON_EXE) 로 모듈 확인
        if ! "$PYTHON_EXE" -c "import ${module_name}" 2>/dev/null; then
            log_warning "${pkg} (모듈명: ${module_name}) 패키지가 없습니다. 설치 중..."
            "$PYTHON_EXE" -m pip install ${pkg} --quiet 2>/dev/null || \
            log_warning "${pkg} 설치 실패. 인터넷 연결이나 권한을 확인하세요."
        fi
    done
    
    log_success "의존성 확인 완료"
}

# 설정 파일 확인
check_config_files() {
    log_info "설정 파일 확인 중..."
    
    if [ ! -f "${INVENTORY_FILE}" ]; then
        log_warning "인벤토리 파일을 찾을 수 없습니다: ${INVENTORY_FILE}"
        log_info "기본 템플릿을 생성합니다..."
        mkdir -p "$(dirname "${INVENTORY_FILE}")"
        touch "${INVENTORY_FILE}"
    fi
    
    if [ ! -f "${CHECKS_FILE}" ]; then
        log_error "점검 항목 파일을 찾을 수 없습니다: ${CHECKS_FILE}"
        exit 1
    fi
    
    log_success "설정 파일 확인 완료"
}

# 출력 디렉토리 생성
setup_output_dir() {
    mkdir -p "${OUTPUT_DIR}"
}

# SSH 키 확인
check_ssh_key() {
    local ssh_key="${SSH_PRIVATE_KEY_PATH:-$HOME/.ssh/id_rsa}"
    
    ssh_key="${ssh_key/#\~/$HOME}"
    
    if [ -f "${ssh_key}" ]; then
        log_success "SSH 키 확인 완료: ${ssh_key}"
        return
    fi
    
    # 키가 없어도 데모 모드 등에서는 동작해야 하므로 경고만 출력
    log_info "SSH 키(${ssh_key})가 확인되지 않았습니다. (데모 모드 시 무시 가능)"
}

# 도움말
show_help() {
    cat << EOF
CMP 인프라 정기점검 보고서 생성기

사용법:
    $0 [옵션]

옵션:
    --type, -t <weekly|monthly>    보고서 유형 (기본: weekly)
    --demo                         데모 모드 (샘플 데이터 사용)
    --env, -e <dev|stg|prd|all>    점검할 환경 (기본: all)
    --output-dir, -o <경로>        보고서 출력 디렉토리
    --json                         JSON 형식 출력
    --quiet, -q                    최소 출력
    --help, -h                     도움말 표시

EOF
}

# 메인 실행
main() {
    echo ""
    echo "================================================================"
    echo "  🔍 CMP 인프라 정기점검 시스템"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================================"
    echo ""
    
    check_dependencies
    check_config_files
    setup_output_dir
    check_ssh_key
    
    # Python 스크립트 실행
    # (주의: scripts/main.py 경로에 앞서 수정한 파이썬 코드가 있어야 합니다)
    "$PYTHON_EXE" "${PYTHON_SCRIPT}" \
        --inventory "${INVENTORY_FILE}" \
        --checks "${CHECKS_FILE}" \
        --output-dir "${OUTPUT_DIR}" \
        "$@"
    
    local exit_code=$?
    
    echo ""
    if [ $exit_code -eq 0 ]; then
        log_success "점검 완료: 모든 항목 정상"
    elif [ $exit_code -eq 1 ]; then
        log_warning "점검 완료: 경고 항목 발견"
    else
        log_error "점검 완료: 위험 항목 발견 또는 실행 오류"
    fi
    
    exit $exit_code
}

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_help
    exit 0
fi

main "$@"