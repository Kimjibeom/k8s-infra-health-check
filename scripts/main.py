#!/usr/bin/env python3
"""
CMP 인프라 정기점검 - 메인 스크립트
OS, Kubernetes, K8s 서비스, CI/CD, DB 점검 및 보고서 생성

사용법:
    python main.py                      # 기본 실행
    python main.py --type monthly       # 월간 보고서
    python main.py --env dev            # 특정 환경만 점검
"""

import argparse
import os
import sys
import yaml
from datetime import datetime

# 현재 스크립트의 경로를 파이썬 경로에 추가하여 모듈 import 지원
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# 모듈 로드 (같은 폴더에 위치한다고 가정)
try:
    from checker import CMPInfraChecker
    from report_generator import CMPReportGenerator, ReportConfig, generate_reports
except ImportError as e:
    print(f"❌ 필수 모듈을 로드할 수 없습니다: {e}")
    sys.exit(1)


def load_inventory_config(inventory_path: str) -> dict:
    """인벤토리 설정 로드"""
    try:
        with open(inventory_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}  
    except Exception as e:
        print(f"⚠️  설정 로드 중 오류 발생 (무시하고 진행): {e}")
        return {}


def create_report_config(inventory: dict, report_type: str, output_dir: str = None) -> ReportConfig:
    """보고서 설정 생성"""
    report_conf = inventory.get('report', {})
    
    return ReportConfig(
        report_type=report_type or report_conf.get('type', 'weekly'),
        company_name=report_conf.get('company_name', 'CMP 인프라'),
        team_name=report_conf.get('team_name', '클라우드서비스팀'),
        output_dir=output_dir or report_conf.get('output_dir', './output')
    )


def main():
    parser = argparse.ArgumentParser(description='CMP 인프라 정기점검 보고서 생성')
    
    parser.add_argument('--inventory', '-i',
        default=os.path.join(os.path.dirname(SCRIPT_DIR), 'config', 'inventory.yaml'),
        help='인벤토리 설정 파일 경로 (기본: config/inventory.yaml)')
    parser.add_argument('--checks', '-c',
        default=os.path.join(os.path.dirname(SCRIPT_DIR), 'config', 'check_items.yaml'),
        help='점검 항목 설정 파일 경로')
    parser.add_argument('--type', '-t', choices=['weekly', 'monthly'], 
        default='weekly', help='보고서 유형')
    parser.add_argument('--output-dir', '-o', help='보고서 출력 디렉토리')
    parser.add_argument('--env', '-e', choices=['dev', 'stg', 'prd', 'gpu', 'all'],
        default='all', help='점검할 환경 (--cluster 미지정 시 사용, gpu=테스트용)')
    parser.add_argument('--cluster', action='append', default=None, metavar='CLUSTER',
        help='점검할 클러스터 (복수 지정 가능, 예: --cluster dev_cluster --cluster stg_cluster). 지정 시 --env 무시')
    parser.add_argument('--json', action='store_true', help='JSON 형식 출력')
    parser.add_argument('--quiet', '-q', action='store_true', help='최소 출력')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.inventory):
        if not args.quiet:
            print(f"❌ 인벤토리 파일을 찾을 수 없습니다: {args.inventory}")
        sys.exit(1)
    
    if not os.path.exists(args.checks):
        if not args.quiet:
            print(f"❌ 점검 항목 파일을 찾을 수 없습니다: {args.checks}")
        sys.exit(1)
    
    inventory = load_inventory_config(args.inventory)
    report_config = create_report_config(inventory, args.type, args.output_dir)
    
    # 출력용 환경 이름: --cluster 사용 시 해당 클러스터명, --env 사용 시 환경명, 미지정 시 ALL
    if args.cluster:
        env_display = ", ".join(args.cluster).upper()
    elif args.env != 'all':
        env_display = args.env.upper()
    else:
        env_display = "ALL"
    
    if not args.quiet:
        print("=" * 70)
        print("🔍 CMP 인프라 정기점검 시작")
        print(f"   보고서 유형: {report_config.report_type}")
        print(f"   회사: {report_config.company_name}")
        print(f"   담당팀: {report_config.team_name}")
        print(f"   점검 환경: {env_display}")
        print("=" * 70)
    
    checker = CMPInfraChecker(
        inventory_path=args.inventory,
        checks_path=args.checks
    )
    
    results = checker.run_all_checks(env_filter=args.env, cluster_filter=args.cluster)
    
    if not results:
        if not args.quiet:
            print("\n" + "=" * 70)
            print("⚠️  진행된 점검 항목이 없습니다 (0건).")
            print(f"    인벤토리 파일({args.inventory})에 서버/클러스터 정보가 있는지 확인해주세요.")
            print("=" * 70)
        sys.exit(0)

    results_dict = checker.to_dict()
    summary = checker.get_summary()
    
    if args.json:
        import json
        output = {
            'summary': summary,
            'results': results_dict,
            'timestamp': datetime.now().isoformat()
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    
    if not args.quiet:
        print("\n" + "=" * 70)
        print("📊 점검 결과 요약")
        print("=" * 70)
        print(f"   총 점검항목: {summary['total']}")
        print(f"   ✅ 정상: {summary['ok']}")
        print(f"   ⚠️  경고: {summary['warning']}")
        print(f"   ❌ 위험: {summary['critical']}")
        print(f"   ❓ 확인불가: {summary['unknown']}")
        print("=" * 70)
        
        if summary.get('by_environment'):
            print("\n📂 환경별 결과:")
            for env, env_summary in summary.get('by_environment', {}).items():
                print(f"   {env}: ✅{env_summary['ok']} ⚠️{env_summary['warning']} ❌{env_summary['critical']} ❓{env_summary['unknown']}")
        
        if summary.get('by_category'):
            print("\n📂 카테고리별 결과:")
            for cat, cat_summary in summary.get('by_category', {}).items():
                print(f"   {cat}: ✅{cat_summary['ok']} ⚠️{cat_summary['warning']} ❌{cat_summary['critical']} ❓{cat_summary['unknown']}")
    
    if not args.quiet:
        print("\n📝 보고서 생성 중...")
    
    try:
        generated_files = generate_reports(results_dict, summary, report_config)
        
        if not args.quiet:
            print("✅ 보고서 생성 완료:")
            for fmt, path in generated_files.items():
                print(f"   - {fmt.upper()}: {path}")
    except Exception as e:
        if not args.quiet:
            print(f"❌ 보고서 생성 실패: {e}")
            import traceback
            traceback.print_exc()

    issues = [r for r in results_dict if r.get('상태') in ['경고', '위험']]
    if issues and not args.quiet:
        print("\n" + "=" * 70)
        print("🚨 조치 필요 항목")
        print("=" * 70)
        for issue in issues:
            status = issue.get('상태', '')
            icon = "⚠️" if status == '경고' else "❌"
            print(f"{icon} [{issue.get('점검ID')}] {issue.get('점검항목')}")
            print(f"   환경: {issue.get('환경', '')}")
            print(f"   대상: {issue.get('점검대상', '')}")
            print(f"   상태: {status}")
            print(f"   메시지: {issue.get('결과메시지', '')}")
            print()
    
    if not args.quiet:
        print("=" * 70)
        print("✅ 점검 완료")
        print("=" * 70)
    
    if summary['critical'] > 0:
        sys.exit(2)
    elif summary['warning'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()