#!/usr/bin/env python3
"""
output 디렉터리의 CSV 보고서를 읽어 기존 report_generator와 동일한 형식의 DOCX로 변환
사용법: python3 csv_to_docx.py [CSV파일경로]
        CSV 경로 생략 시 output/ 내 가장 최근 cmp_infra_check_*.csv 사용
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# 프로젝트 루트 또는 scripts에서 실행 시 import 경로 보정
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

from scripts.report_generator import CMPReportGenerator, ReportConfig, DOCX_AVAILABLE


def parse_csv_metadata(lines: List[str]) -> Tuple[Dict, List[str]]:
    """
    CSV 앞부분 # 주석 라인에서 메타데이터 파싱.
    (parsed_metadata, 나머지_라인들) 반환.
    """
    metadata = {
        'title': '',
        'created': '',
        'company_name': 'CMP 인프라',
        'team_name': '클라우드서비스팀',
        'total': 0,
        'ok': 0,
        'warning': 0,
        'critical': 0,
        'unknown': 0,
    }
    rest = []
    in_header = True

    for line in lines:
        if in_header and line.startswith('#'):
            s = line[1:].strip()
            if s.startswith('생성일시:'):
                metadata['created'] = s.replace('생성일시:', '').strip()
            elif s.startswith('회사:'):
                metadata['company_name'] = s.replace('회사:', '').strip()
            elif s.startswith('담당팀:'):
                metadata['team_name'] = s.replace('담당팀:', '').strip()
            elif '총 점검항목:' in s:
                m = re.search(r'총 점검항목:\s*(\d+)', s)
                if m:
                    metadata['total'] = int(m.group(1))
            elif '정상:' in s and '경고:' in s:
                m = re.search(r'정상:\s*(\d+).*?경고:\s*(\d+).*?위험:\s*(\d+).*?확인불가:\s*(\d+)', s)
                if m:
                    metadata['ok'] = int(m.group(1))
                    metadata['warning'] = int(m.group(2))
                    metadata['critical'] = int(m.group(3))
                    metadata['unknown'] = int(m.group(4))
            else:
                # 제목 라인 (첫 번째 유의미한 # 라인으로 가정)
                if s and not metadata['title']:
                    metadata['title'] = s
            continue
        in_header = False
        rest.append(line)

    return metadata, rest


def load_csv_results(filepath: str) -> Tuple[List[Dict], Dict, Dict]:
    """
    output용 CSV 파일을 읽어 (results, summary, metadata) 반환.
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        all_lines = f.readlines()

    metadata, rest = parse_csv_metadata(all_lines)

    # 빈 줄 건너뛰기
    rest = [line for line in rest if line.strip()]
    if not rest:
        return [], _build_summary([], metadata), metadata

    reader = csv.DictReader(rest)
    results = list(reader)

    summary = _build_summary(results, metadata)
    return results, summary, metadata


def _build_summary(results: List[Dict], metadata: Dict) -> Dict:
    """results와 파싱된 metadata로 summary 딕셔너리 생성."""
    by_env = defaultdict(lambda: {'ok': 0, 'warning': 0, 'critical': 0, 'unknown': 0})
    by_cat = defaultdict(lambda: {'ok': 0, 'warning': 0, 'critical': 0, 'unknown': 0})

    for r in results:
        status = r.get('상태', 'unknown')
        if status == '정상':
            key = 'ok'
        elif status == '경고':
            key = 'warning'
        elif status == '위험':
            key = 'critical'
        else:
            key = 'unknown'

        env = r.get('환경', 'Unknown')
        cat = r.get('카테고리', 'Unknown')
        by_env[env][key] += 1
        by_cat[cat][key] += 1

    return {
        'total': metadata.get('total', len(results)),
        'ok': metadata.get('ok', sum(1 for r in results if r.get('상태') == '정상')),
        'warning': metadata.get('warning', sum(1 for r in results if r.get('상태') == '경고')),
        'critical': metadata.get('critical', sum(1 for r in results if r.get('상태') == '위험')),
        'unknown': metadata.get('unknown', sum(1 for r in results if r.get('상태') not in ('정상', '경고', '위험'))),
        'by_environment': dict(by_env),
        'by_category': dict(by_cat),
    }


def get_latest_csv(output_dir: str) -> str:
    """output_dir 내 cmp_infra_check_*.csv 중 수정 시간 기준 최신 파일 경로 반환."""
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"디렉터리가 없습니다: {output_dir}")

    candidates = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith('cmp_infra_check_') and f.endswith('.csv')
    ]
    if not candidates:
        raise FileNotFoundError(f"CSV 파일이 없습니다: {output_dir}")

    return max(candidates, key=os.path.getmtime)


class CSVToDocxGenerator(CMPReportGenerator):
    """CSV 파일명/메타데이터에 맞춰 DOCX를 생성하는 생성기."""

    def __init__(self, csv_path: str, metadata: Dict, config: ReportConfig = None):
        super().__init__(config)
        self._filename_prefix = os.path.splitext(os.path.basename(csv_path))[0]
        self._report_title = metadata.get('title') or self._get_report_title()

    def _get_filename_prefix(self) -> str:
        return self._filename_prefix

    def _get_report_title(self) -> str:
        return self._report_title


def generate_docx_from_csv(csv_path: str, output_path: str = None) -> str:
    """
    CSV 파일을 읽어 동일한 형식의 DOCX로 변환하여 저장.
    output_path 미지정 시 CSV와 같은 디렉터리, 같은 기본이름.docx 로 저장.
    """
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx 라이브러리가 설치되지 않았습니다. pip3.10 install python-docx")

    results, summary, metadata = load_csv_results(csv_path)

    output_dir = os.path.dirname(os.path.abspath(csv_path))
    if output_path is None:
        base = os.path.splitext(os.path.basename(csv_path))[0]
        output_path = os.path.join(output_dir, f"{base}.docx")

    config = ReportConfig(
        company_name=metadata.get('company_name', 'CMP 인프라'),
        team_name=metadata.get('team_name', '클라우드서비스팀'),
        output_dir=os.path.dirname(output_path),
    )
    generator = CSVToDocxGenerator(csv_path, metadata, config)
    # generate_docx는 내부에서 self._get_filename_prefix()로 파일명을 만드므로,
    # 우리가 원하는 output_path로 저장하려면 output_dir를 해당 디렉터리로 하고
    # 파일명 prefix를 output_path의 basename에서 확장자 제거한 값으로 맞춤 (이미 CSVToDocxGenerator에서 함)
    # 단, output_dir가 다를 수 있으므로 config.output_dir를 output_path의 디렉터리로 설정했음.
    # _get_filename_prefix가 base만 반환하므로 파일은 config.output_dir / (prefix + ".docx")에 저장됨 → 원하는 path와 일치
    generator.generate_docx(results, summary)

    # 실제 저장 경로 (generator가 만든 경로)
    actual_path = os.path.join(config.output_dir, f"{generator._get_filename_prefix()}.docx")
    return actual_path


def main():
    parser = argparse.ArgumentParser(description='CSV 보고서를 DOCX 형식으로 변환')
    parser.add_argument(
        'csv_file',
        nargs='?',
        default=None,
        help='변환할 CSV 파일 경로 (생략 시 output/ 내 최신 cmp_infra_check_*.csv 사용)',
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='저장할 DOCX 파일 경로 (생략 시 CSV와 같은 위치, 같은 이름.docx)',
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(base_dir, 'output')

    if args.csv_file:
        csv_path = os.path.abspath(args.csv_file)
        if not os.path.isfile(csv_path):
            print(f"오류: 파일을 찾을 수 없습니다: {csv_path}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            csv_path = get_latest_csv(output_dir)
        except FileNotFoundError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"CSV 읽는 중: {csv_path}")
    try:
        docx_path = generate_docx_from_csv(csv_path, args.output)
        print(f"DOCX 생성 완료: {docx_path}")
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
