#!/usr/bin/env python3
"""
CMP 인프라 점검 모듈
OS, Kubernetes 클러스터, K8s 서비스, CI/CD, DB 점검
"""

import yaml
import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

# ssh_executor 모듈이 같은 경로에 있다고 가정
from ssh_executor import get_executor, RemoteExecutor, ConnectionResult


class CheckStatus(Enum):
    OK = "정상"
    WARNING = "경고"
    CRITICAL = "위험"
    UNKNOWN = "확인불가"


@dataclass
class CheckResult:
    """점검 결과"""
    check_id: str
    name: str
    category: str
    subcategory: str
    description: str
    status: CheckStatus
    value: str
    threshold: Optional[float]
    unit: str
    message: str
    target: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    severity: str = "medium"


class CMPInfraChecker:
    """CMP 인프라 점검 클래스"""
    
    def __init__(self, 
                 inventory_path: str = "config/gpu-inventory.yaml",
                 checks_path: str = "config/check_items.yaml"):
        
        self.inventory_path = inventory_path
        self.checks_config = self._load_config(checks_path)
        self.executor = get_executor(inventory_path=inventory_path)
        self.results: List[CheckResult] = []
        
    def _load_config(self, path: str) -> dict:
        """설정 파일 로드"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
    
    def _evaluate_threshold(self, value: str, threshold: float, 
                           check_id: str) -> Tuple[CheckStatus, str]:
        """임계치 기반 상태 평가"""
        try:
            clean_val = str(value).replace('%', '').replace('개', '').strip()
            match = re.search(r'(\d+(\.\d+)?)', clean_val)
            
            if not match:
                return CheckStatus.UNKNOWN, "값 파싱 실패"
                
            numeric_value = float(match.group(1))
            
            zero_is_ok = ['OS-005', 'K8S-006', 'SVC-004', 
                          'SVC-006', 'SVC-007', 'SVC-008', 'SVC-010']
            
            if check_id in zero_is_ok:
                if numeric_value == 0:
                    return CheckStatus.OK, "정상"
                elif numeric_value <= 3:
                    return CheckStatus.WARNING, f"주의 필요 ({numeric_value}개)"
                else:
                    return CheckStatus.CRITICAL, f"즉시 조치 필요 ({numeric_value}개)"
            else:
                # 'threshold'는 YAML에 정의된 '위험' 수준의 임계치입니다.
                critical_level = float(threshold)
                # '경고' 수준은 '위험' 수준의 90%로 설정합니다.
                warning_level = critical_level * 0.9

                if numeric_value >= critical_level:
                    return CheckStatus.CRITICAL, f"임계치 초과 ({numeric_value:.1f}% / {critical_level}%)"
                elif numeric_value >= warning_level:
                    return CheckStatus.WARNING, f"임계치 근접 ({numeric_value:.1f}% / {critical_level}%)"
                else:
                    return CheckStatus.OK, "정상 범위"
                    
        except Exception:
            return CheckStatus.UNKNOWN, "값 파싱 실패"
    
    def _evaluate_expected(self, output: str, expected: str) -> Tuple[CheckStatus, str]:
        """기대값 기반 상태 평가"""
        if not output or output == 'N/A':
            return CheckStatus.UNKNOWN, "데이터 없음"
        
        lines = [l.strip() for l in output.strip().split('\n') if l.strip()]
        if not lines:
            return CheckStatus.UNKNOWN, "점검 대상 없음"
        
        total = len(lines)
        ok_count = sum(1 for line in lines if expected in line)
        
        if ok_count == total:
            return CheckStatus.OK, f"모두 정상 ({ok_count}/{total})"
        elif ok_count >= total * 0.7:
            return CheckStatus.WARNING, f"일부 이상 ({ok_count}/{total} 정상)"
        else:
            return CheckStatus.CRITICAL, f"다수 이상 ({total - ok_count}개 문제)"

    # ==========================================
    # OS 점검
    # ==========================================
    def check_os(self, servers: List[Dict], env_name: str = "") -> List[CheckResult]:
        results = []
        if not servers: return results
        os_checks = self.checks_config.get('os_checks', [])
        
        for server in servers:
            hostname = server.get('hostname', '')
            ip = server.get('ip', '')
            
            # IP가 없으면 Skip
            if not ip: continue

            port = server.get('ssh_port', server.get('port', 22))
            server_name = server.get('name', hostname)
            category = server.get('category', 'OS')
            
            for check in os_checks:
                result = self._run_os_check(check, hostname, ip, port, 
                                               server_name, category, env_name)
                results.append(result)
        return results
    
    def _run_os_check(self, check: dict, hostname: str, ip: str, port: int,
                      server_name: str, category: str, env_name: str) -> CheckResult:
        check_id = check['id']
        conn_result = self.executor.execute_ssh(hostname, ip, check['command'], port)
        
        if not conn_result.success:
            return CheckResult(
                check_id=check_id,
                name=check['name'],
                category=category,
                subcategory=env_name,
                description=check['description'],
                status=CheckStatus.UNKNOWN,
                value="N/A",
                threshold=check.get('threshold'),
                unit=check.get('unit', ''),
                message=conn_result.error_message or "연결 실패",
                target=server_name,
                severity=check.get('severity', 'medium')
            )
        
        value = conn_result.stdout
        threshold = check.get('threshold')
        
        if threshold is not None:
            status, message = self._evaluate_threshold(value, threshold, check_id)
        else:
            status = CheckStatus.OK
            message = "정보 수집 완료"
        
        return CheckResult(
            check_id=check_id,
            name=check['name'],
            category=category,
            subcategory=env_name,
            description=check['description'],
            status=status,
            value=value.strip(),
            threshold=threshold,
            unit=check.get('unit', ''),
            message=message,
            target=server_name,
            severity=check.get('severity', 'medium')
        )

    # ==========================================
    # Kubernetes 점검 (로컬 실행 - Bastion에서 해당 클러스터 kubectl 사용)
    # ==========================================
    def check_k8s_cluster(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster: return results
        
        env_name = cluster.get('env', cluster_key.upper())
        k8s_checks = self.checks_config.get('k8s_cluster_checks', [])
        
        # Bastion 로컬에서 kubectl 실행 (해당 Bastion의 기본 kubeconfig/컨텍스트 사용)
        for check in k8s_checks:
            result = self._run_k8s_check_local(check, env_name)
            results.append(result)
        return results

    def _run_k8s_check_local(self, check: dict, env_name: str) -> CheckResult:
        """K8s 점검 - Bastion 로컬 실행"""
        check_id = check['id']
        conn_result = self.executor.execute_local(check['command'])
        
        if check_id == 'K8S-005' and conn_result.return_code == 1:
            conn_result.success = True
            conn_result.stdout = "0"

        if not conn_result.success:
            return CheckResult(
                check_id=check_id, name=check['name'], category="Kubernetes", subcategory=env_name,
                description=check['description'], status=CheckStatus.UNKNOWN, value="N/A",
                threshold=check.get('threshold'), unit=check.get('unit', ''),
                message=conn_result.error_message or "kubectl 실행 실패",
                target=f"{env_name} Cluster", severity=check.get('severity', 'medium')
            )
        
        value = conn_result.stdout
        expected = check.get('expected')
        threshold = check.get('threshold')
        
        if expected:
            status, message = self._evaluate_expected(value, expected)
        elif threshold is not None:
            status, message = self._evaluate_threshold(value, threshold, check_id)
        else:
            status = CheckStatus.OK
            message = "정보 수집 완료"
        
        return CheckResult(
            check_id=check_id, name=check['name'], category="Kubernetes", subcategory=env_name,
            description=check['description'], status=status, value=value[:200] if value else "N/A",
            threshold=threshold, unit=check.get('unit', ''), message=message,
            target=f"{env_name} Cluster", severity=check.get('severity', 'medium')
        )

    def check_k8s_services(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster: return results
        
        env_name = cluster.get('env', cluster_key.upper())
        svc_checks = self.checks_config.get('k8s_service_checks', [])
        
        for check in svc_checks:
            result = self._run_svc_check_local(check, env_name)
            results.append(result)
        return results

    def check_k8s_apps(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster: return results
        
        env_name = cluster.get('env', cluster_key.upper())
        # config/check_items.yaml에서 k8s_app_checks 섹션을 읽어옴
        app_checks = self.checks_config.get('k8s_app_checks', [])
        
        for check in app_checks:
            result = self._run_k8s_app_check_local(check, env_name)
            results.append(result)
        return results

    def _run_k8s_app_check_local(self, check: dict, env_name: str) -> CheckResult:
        """앱 점검 실행 로직"""
        check_id = check['id']
        conn_result = self.executor.execute_local(check['command'])
        
        if not conn_result.success:
            return CheckResult(
                check_id=check_id,
                name=check['name'],
                category=check.get('category', 'Application'),
                subcategory=env_name,
                description=check['description'],
                status=CheckStatus.UNKNOWN,
                value="N/A",
                threshold=check.get('threshold'),
                unit=check.get('unit', ''),
                message=conn_result.error_message or "점검 실패",
                target=f"{env_name} Apps",
                severity=check.get('severity', 'medium')
            )
        
        # 결과값(개수) 파싱
        value = conn_result.stdout
        threshold = check.get('threshold')
        
        # 임계치(기대하는 파드 개수)와 비교
        if threshold is not None:
            # 값이 임계치보다 크거나 같으면 정상 (최소 n개 실행 중이어야 함)
            try:
                current_count = int(value.strip())
                if current_count >= threshold:
                    status = CheckStatus.OK
                    message = f"정상 (현재 {current_count}개)"
                else:
                    status = CheckStatus.CRITICAL
                    message = f"개수 부족 (현재 {current_count}/{threshold})"
            except ValueError:
                status = CheckStatus.UNKNOWN
                message = "결과값 파싱 오류"
        else:
            status = CheckStatus.OK
            message = "정보 수집 완료"
            
        return CheckResult(
            check_id=check_id,
            name=check['name'],
            category=check.get('category', 'Application'),
            subcategory=env_name,
            description=check['description'],
            status=status,
            value=value.strip(),
            threshold=threshold,
            unit=check.get('unit', ''),
            message=message,
            target=f"{env_name} Apps",
            severity=check.get('severity', 'medium')
        )

    def _run_svc_check_local(self, check: dict, env_name: str) -> CheckResult:
        """K8s 서비스 점검 - Bastion 로컬 실행"""
        check_id = check['id']
        conn_result = self.executor.execute_local(check['command'])
        
        if not conn_result.success:
            return CheckResult(
                check_id=check_id, name=check['name'], category="Services", subcategory=env_name,
                description=check['description'], status=CheckStatus.UNKNOWN, value="N/A",
                threshold=check.get('threshold'), unit=check.get('unit', ''),
                message=conn_result.error_message or "점검 실패",
                target=f"{env_name} Services", severity=check.get('severity', 'medium')
            )
        
        value = conn_result.stdout
        check_type = check.get('check_type', '')
        threshold = check.get('threshold')
        
        if check_type == 'replica_match':
            if value and value.strip():
                issues = value.strip().split('\n')
                status = CheckStatus.WARNING if len(issues) <= 3 else CheckStatus.CRITICAL
                message = f"불일치 리소스 {len(issues)}개"
            else:
                status = CheckStatus.OK
                value = "모두 정상"
                message = "모든 리소스 정상"
        elif threshold is not None:
            status, message = self._evaluate_threshold(value or '0', threshold, check_id)
        else:
            status = CheckStatus.OK
            message = "정보 수집 완료"
        
        return CheckResult(
            check_id=check_id, name=check['name'], category="Services", subcategory=env_name,
            description=check['description'], status=status, value=value[:200] if value else "0",
            threshold=threshold, unit=check.get('unit', ''), message=message,
            target=f"{env_name} Services", severity=check.get('severity', 'medium')
        )

    # ==========================================
    # CI/CD 서비스 점검
    # ==========================================
    def check_cicd_services(self) -> List[CheckResult]:
        """CI/CD 서비스 점검"""
        results = []
        cicd_servers = self.executor.get_cicd_servers()
        
        if not cicd_servers:
            return results

        for key, server in cicd_servers.items():
            if not server:
                continue

            hostname = server.get('hostname', '')
            ip = server.get('ip', '')
            server_name = server.get('name', key)
            services = server.get('services', [])
            
            if not ip:
                print(f"⚠️  [Skip] {server_name}: IP 정보가 없습니다.")
                continue

            for service in services:
                svc_name = service.get('name', '')
                port = service.get('port', 80)
                
                url = f"http://{ip}:{port}/"
                success, status_code = self.executor.check_http_status(url)
                    
                if success:
                    status = CheckStatus.OK
                    message = "서비스 정상 응답"
                    value = f"{status_code} OK"
                else:
                    if self.executor.check_tcp_port(ip, port):
                        status = CheckStatus.OK
                        message = "포트 응답 정상"
                        value = f"TCP {port} Open"
                    else:
                        status = CheckStatus.CRITICAL
                        message = "서비스 응답 없음"
                        value = "연결 실패"
                
                check_id = f"CICD-{key}-{svc_name}".replace(' ', '_')
                results.append(CheckResult(
                    check_id=check_id,
                    name=f"{svc_name} 서비스",
                    category="CI/CD",
                    subcategory="CI/CD 인프라",
                    description=f"{server_name} {svc_name} 서비스 상태",
                    status=status, value=value, threshold=None, unit="",
                    message=message, target=server_name, severity="critical"
                ))
        return results

    def check_databases(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster: return results
        
        env_name = cluster.get('env', cluster_key.upper())
        databases = cluster.get('databases', [])
        
        for db in databases:
            hostname = db.get('hostname', '')
            ip = db.get('ip', '')
            if not ip: continue

            db_name = db.get('name', '')
            services = db.get('services', [])
            
            for service in services:
                svc_name = service.get('name', 'MySQL')
                port = service.get('port', 3306)
                
                if self.executor.check_tcp_port(ip, port):
                    status = CheckStatus.OK
                    message = "DB 연결 정상"
                    value = f"TCP {port} Open"
                else:
                    status = CheckStatus.CRITICAL
                    message = "DB 연결 실패"
                    value = "연결 불가"
                
                results.append(CheckResult(
                    check_id=f"DB-{env_name[:1]}{db_name[-1:]}",
                    name=f"{svc_name} 연결",
                    category="Database",
                    subcategory=env_name,
                    description=f"{db_name} {svc_name} 포트 연결 확인",
                    status=status, value=value, threshold=None, unit="",
                    message=message, target=f"{env_name} {db_name}", severity="critical"
                ))
        return results

    # ==========================================
    # 인증서 점검 
    # ==========================================
    def check_ssl_certs(self) -> List[CheckResult]:
        results = []
        # 인벤토리 ssl_domains 또는 report.ssl_domains 사용, 없으면 기본 도메인
        target_domains = self.executor.get_ssl_domains()
        if not target_domains:
            target_domains = ["google.com", "example.com"]
        
        ssl_checks = self.checks_config.get('ssl_checks', [])
        if not ssl_checks: return results

        for domain in target_domains:
            for check in ssl_checks:
                cmd = check['command'].replace('{domain}', domain)
                
                conn_result = self.executor.execute_local(cmd)
                    
                if conn_result.success:
                    value = conn_result.stdout.strip()
                    try:
                        expire_date = datetime.strptime(value, '%b %d %H:%M:%S %Y %Z')
                        days_left = (expire_date - datetime.now()).days
                        
                        if days_left < 30:
                            status = CheckStatus.CRITICAL
                            message = f"만료 임박 ({days_left}일 남음)"
                        elif days_left < 60:
                            status = CheckStatus.WARNING
                            message = f"갱신 필요 ({days_left}일 남음)"
                        else:
                            status = CheckStatus.OK
                            message = f"정상 ({days_left}일 남음)"
                    except Exception:
                        status = CheckStatus.WARNING
                        message = "날짜 파싱 실패"
                else:
                    value = "N/A"
                    status = CheckStatus.UNKNOWN
                    message = "연결 실패"

                results.append(CheckResult(
                    check_id=f"{check['id']}-{domain}",
                    name=f"{domain} SSL",
                    category="SSL",
                    subcategory="인증서",
                    description=check['description'],
                    status=status,
                    value=value,
                    threshold=None,
                    unit="",
                    message=message,
                    target=domain,
                    severity=check.get('severity', 'high')
                ))
        return results

    # ==========================================
    # 버전 점검  
    # ==========================================
    def check_sw_versions(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster: return results
        env_name = cluster.get('env', cluster_key.upper())
        
        sw_checks = self.checks_config.get('sw_version_checks', [])
        
        # 1. OS 레벨 점검 (모든 마스터/워커 노드에서 실행하거나, 대표 노드 하나에서만 실행)
        masters = cluster.get('masters', [])
        target_node = masters[0] if masters else None
        
        if target_node:
            for check in sw_checks:
                if "kubectl" in check['command']: continue # kubectl 명령은 아래에서 별도 처리
                
                hostname = target_node.get('hostname')
                ip = target_node.get('ip')
                
                res = self.executor.execute_ssh(hostname, ip, check['command'],
                                                target_node.get('ssh_port', target_node.get('port', 22)))
                value = res.stdout.strip() if res.success else "확인 불가"
                status = CheckStatus.OK if res.success else CheckStatus.UNKNOWN

                results.append(CheckResult(
                    check_id=check['id'],
                    name=check['name'],
                    category="SW Version",
                    subcategory=env_name,
                    description=check['description'],
                    status=status,
                    value=value,
                    threshold=None, unit="", message="버전 정보",
                    target=hostname, severity=check.get('severity', 'medium')
                ))

        # 2. 클러스터 레벨 점검 (Pod 이미지 등 - kubectl 사용)
        for check in sw_checks:
            if "kubectl" not in check['command']: continue
            res = self.executor.execute_local(check['command'])
            raw_value = res.stdout.strip()
            lines = raw_value.split('\n')
            count = len(lines)
            value = f"총 {count}개 이미지 (상세 생략)" 

            results.append(CheckResult(
                check_id=check['id'],
                name=check['name'],
                category="SW Version",
                subcategory=env_name,
                description=check['description'],
                status=CheckStatus.OK,
                value=value, # 전체 리스트 대신 요약본 출력
                threshold=None, unit="개", 
                message=f"이미지 {count}개 추출 완료",
                target=f"{env_name} Cluster", severity=check.get('severity', 'medium')
            ))
            
        return results

    # ==========================================
    # 스토리지 점검 (storage_checks: command / tcp_port)
    # ==========================================
    def check_storage_details(self, cluster_key: str) -> List[CheckResult]:
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster:
            return results
        env_name = cluster.get('env', cluster_key.upper())
        storage_checks = self.checks_config.get('storage_checks', [])
        # tcp_port 점검 시 사용할 IP (클러스터 첫 마스터 또는 localhost)
        masters = cluster.get('masters', [])
        storage_host = masters[0].get('ip', '127.0.0.1') if masters else '127.0.0.1'

        for check in storage_checks:
            check_id = check.get('id', '')
            if check.get('check_type') == 'tcp_port':
                port = check.get('port')
                if port is None:
                    continue
                ok = self.executor.check_tcp_port(storage_host, port)
                value = f"TCP {port} Open" if ok else "연결 불가"
                status = CheckStatus.OK if ok else CheckStatus.CRITICAL
                message = "포트 응답 정상" if ok else "포트 연결 실패"
            elif 'command' in check:
                conn_result = self.executor.execute_local(check['command'])
                if conn_result.success:
                    raw_value = conn_result.stdout.strip()
                    if raw_value:
                        value = raw_value
                        threshold = check.get('threshold')
                        if threshold is not None:
                            try:
                                n = int(value)
                                status = CheckStatus.OK if n >= threshold else CheckStatus.CRITICAL
                                message = f"정상 ({n}개)" if n >= threshold else f"부족 (현재 {n}/{threshold})"
                            except ValueError:
                                status = CheckStatus.OK
                                message = "스토리지 할당 현황"
                        else:
                            status = CheckStatus.OK
                            message = "스토리지 할당 현황"
                    else:
                        value = "0"
                        status = CheckStatus.CRITICAL if (check.get('threshold') or 0) > 0 else CheckStatus.OK
                        message = "NFS 마운트 없음"
                else:
                    value = "N/A"
                    status = CheckStatus.UNKNOWN
                    message = conn_result.error_message or "조회 실패"
            else:
                continue

            results.append(CheckResult(
                check_id=check_id,
                name=check.get('name', ''),
                category="Storage",
                subcategory=env_name,
                description=check.get('description', ''),
                status=status,
                value=value,
                threshold=check.get('threshold'),
                unit=check.get('unit', ''),
                message=message,
                target=f"{env_name} Cluster",
                severity=check.get('severity', 'info')
            ))
        # 인벤토리 nfs_storage 호스트 연결 확인 (hostname 또는 ip로 2049 포트)
        nfs_cfg = cluster.get('nfs_storage')
        if nfs_cfg:
            host = nfs_cfg.get('ip') or nfs_cfg.get('hostname')
            if host:
                ok = self.executor.check_tcp_port(host, 2049)
                status = CheckStatus.OK if ok else CheckStatus.CRITICAL
                value = "TCP 2049 Open" if ok else "연결 불가"
                message = "NFS 스토리지 서버 연결 정상" if ok else "NFS 스토리지 서버 연결 실패"
                results.append(CheckResult(
                    check_id="STG-NFS-HOST",
                    name=nfs_cfg.get('name', 'NFS Storage') + " 서버",
                    category="Storage",
                    subcategory=env_name,
                    description="인벤토리 nfs_storage 호스트 NFS 포트(2049) 확인",
                    status=status,
                    value=value,
                    threshold=None,
                    unit="",
                    message=message,
                    target=str(host),
                    severity="critical"
                ))
        return results

    # ==========================================
    # Bastion 서비스 점검 (인벤토리 bastion.services 포트 확인)
    # ==========================================
    def check_bastion_services(self, cluster_key: str) -> List[CheckResult]:
        """클러스터 Bastion에 정의된 서비스(NFS, RPC 등) 포트 연결 확인"""
        results = []
        cluster = self.executor.get_cluster_info(cluster_key)
        if not cluster:
            return results
        bastion = cluster.get('bastion')
        if not bastion:
            return results
        services = bastion.get('services', [])
        if not services:
            return results
        ip = bastion.get('ip', '')
        if not ip:
            return results
        env_name = cluster.get('env', cluster_key.upper())
        bastion_name = bastion.get('name', 'Bastion')
        for svc in services:
            port = svc.get('port')
            if port is None:
                continue
            svc_name = svc.get('name', f'Port {port}')
            ok = self.executor.check_tcp_port(ip, port)
            status = CheckStatus.OK if ok else CheckStatus.CRITICAL
            value = f"TCP {port} Open" if ok else "연결 불가"
            message = "포트 응답 정상" if ok else "포트 연결 실패"
            results.append(CheckResult(
                check_id=f"BASTION-{env_name}-{svc_name}".replace(' ', '_'),
                name=f"{svc_name} (Bastion)",
                category="Bastion",
                subcategory=env_name,
                description=f"{bastion_name} {svc_name} 포트 {port} 확인",
                status=status,
                value=value,
                threshold=None,
                unit="",
                message=message,
                target=bastion_name,
                severity="high"
            ))
        return results

    # ==========================================
    # 전체 점검 실행 (로직 흐름 제어)
    # ==========================================
    def run_all_checks(self, env_filter: str = 'all', cluster_filter: Optional[List[str]] = None) -> List[CheckResult]:
        """모든 점검 실행 - Inventory 누락 시 Skip 처리. env_filter: dev|stg|prd|all. cluster_filter 지정 시 해당 클러스터만 점검."""
        self.results = []
        
        # 1. CI/CD 서비스 점검
        cicd_servers = self.executor.get_cicd_servers()
        has_valid_cicd = False
        if cicd_servers:
            for _, srv in cicd_servers.items():
                if srv and srv.get('ip'):
                    has_valid_cicd = True
                    break
        
        if not has_valid_cicd:
            print("⚠️  [Skip] Inventory에 유효한 CI/CD 서버 정보가 없어 건너뜁니다.")
        else:
            print("📋 CI/CD 서비스 점검 중...")
            self.results.extend(self.check_cicd_services())

        print("📋 SSL 인증서 점검 중...")
        self.results.extend(self.check_ssl_certs())
        
        # 2. 클러스터 점검: 인벤토리에 정의된 클러스터만 대상
        all_environments = [
            ('dev_cluster', '개발 클러스터(DEV)'),
            ('stg_cluster', '스테이징 클러스터(STG)'),
            ('prd_cluster', '운영 클러스터(PRD)')
        ]
        clusters_in_inventory = [(k, l) for k, l in all_environments if self.executor.get_cluster_info(k)]
        # --cluster 지정 시 해당 클러스터만, 미지정 시 --env 기준
        if cluster_filter:
            allowed_keys = set(cluster_filter)
        else:
            env_map = {'dev': ['dev_cluster'], 'stg': ['stg_cluster'], 'prd': ['prd_cluster'], 'all': ['dev_cluster', 'stg_cluster', 'prd_cluster']}
            allowed_keys = set(env_map.get(env_filter, env_map['all']))
        environments = [(k, l) for k, l in clusters_in_inventory if k in allowed_keys]

        for cluster_key, label in environments:
            cluster_info = self.executor.get_cluster_info(cluster_key)
            print(f"📋 {label} 점검 중...")
            
            # OS 점검 대상 서버 수집
            servers = []
            env_short = cluster_info.get('env', 'UNKNOWN')
            
            for m in cluster_info.get('masters', []):
                servers.append({**m, 'category': f'{env_short} Master'})
            for w in cluster_info.get('workers', []):
                servers.append({**w, 'category': f'{env_short} Worker'})
            
            # 각 영역별 점검 수행
            self.results.extend(self.check_os(servers, env_short))
            self.results.extend(self.check_k8s_cluster(cluster_key))
            self.results.extend(self.check_k8s_services(cluster_key))
            self.results.extend(self.check_k8s_apps(cluster_key))
            self.results.extend(self.check_databases(cluster_key))
            self.results.extend(self.check_sw_versions(cluster_key))
            self.results.extend(self.check_storage_details(cluster_key))
            self.results.extend(self.check_bastion_services(cluster_key))
            
        return self.results
    
    def get_summary(self) -> Dict[str, Any]:
        """점검 결과 요약"""
        if not self.results:
            return {'total':0, 'ok':0, 'warning':0, 'critical':0, 'unknown':0}
        
        summary = {
            'total': len(self.results),
            'ok': sum(1 for r in self.results if r.status == CheckStatus.OK),
            'warning': sum(1 for r in self.results if r.status == CheckStatus.WARNING),
            'critical': sum(1 for r in self.results if r.status == CheckStatus.CRITICAL),
            'unknown': sum(1 for r in self.results if r.status == CheckStatus.UNKNOWN),
            'by_environment': {},
            'by_category': {}
        }
        
        for r in self.results:
            env = r.subcategory
            if env not in summary['by_environment']:
                summary['by_environment'][env] = {'ok': 0, 'warning': 0, 'critical': 0, 'unknown': 0}
            
            cat = r.category
            if cat not in summary['by_category']:
                summary['by_category'][cat] = {'ok': 0, 'warning': 0, 'critical': 0, 'unknown': 0}
            
            def increment(d):
                if r.status == CheckStatus.OK: d['ok'] += 1
                elif r.status == CheckStatus.WARNING: d['warning'] += 1
                elif r.status == CheckStatus.CRITICAL: d['critical'] += 1
                else: d['unknown'] += 1
            
            increment(summary['by_environment'][env])
            increment(summary['by_category'][cat])
        
        return summary
    
    def to_dict(self) -> List[Dict]:
        return [
            {
                '점검ID': r.check_id,
                '점검항목': r.name,
                '카테고리': r.category,
                '환경': r.subcategory,
                '점검대상': r.target,
                '설명': r.description,
                '상태': r.status.value,
                '측정값': r.value,
                '임계치': f"{r.threshold}{r.unit}" if r.threshold else "-",
                '결과메시지': r.message,
                '중요도': r.severity,
                '점검시간': r.timestamp
            }
            for r in self.results
        ]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    checker = CMPInfraChecker()
    checker.run_all_checks()
    summary = checker.get_summary()
    print(summary)
    
    print("\n" + "=" * 60)
    print("📊 CMP 인프라 점검 결과 요약")
    print("=" * 60)
    print(f"총 점검 항목: {summary.get('total', 0)}")
    print(f"  ✅ 정상: {summary.get('ok', 0)}")
    print(f"  ⚠️  경고: {summary.get('warning', 0)}")
    print(f"  ❌ 위험: {summary.get('critical', 0)}")
    print(f"  ❓ 확인불가: {summary.get('unknown', 0)}")
    print("=" * 60)