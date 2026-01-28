#!/usr/bin/env python3
"""
SSH 연결 및 원격 명령 실행 모듈
보안을 위해 IP/Port 정보는 별도 설정 파일에서 로드
"""

import subprocess
import socket
import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from pathlib import Path
import re


@dataclass
class SSHConfig:
    """SSH 연결 설정"""
    host: str
    ip: str
    port: int = 22
    user: str = "root"
    private_key_path: str = "~/.ssh/id_rsa"
    connect_timeout: int = 10
    command_timeout: int = 10


@dataclass 
class ConnectionResult:
    """연결 결과"""
    success: bool
    host: str
    ip: str
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    error_message: str = ""
    execution_time: float = 0.0


class RemoteExecutor:
    """원격 서버 명령 실행 클래스"""
    
    def __init__(self, inventory_path: str = "config/dev-inventory.yaml"):
        self.inventory = self._load_inventory(inventory_path)
        self.ssh_config = self._get_ssh_config()
        
    def _load_inventory(self, path: str) -> dict:
        """인벤토리 파일 로드"""
        inventory_path = os.environ.get('CMP_INVENTORY_PATH', path)
        
        try:
            with open(inventory_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 환경변수 치환 (${VAR_NAME} 형식)
            env_pattern = r'\$\{([^}]+)\}'
            def replace_env(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            
            content = re.sub(env_pattern, replace_env, content)
            return yaml.safe_load(content) or {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            print(f"Warning: Failed to load inventory: {e}")
            return {}
    
    def _get_ssh_config(self) -> dict:
        """SSH 설정 가져오기"""
        ssh_conf = self.inventory.get('ssh_config', {})
        return {
            'user': os.environ.get('SSH_USER', ssh_conf.get('default_user', 'root')),
            'private_key_path': os.environ.get('SSH_PRIVATE_KEY_PATH', 
                                              ssh_conf.get('private_key_path', '~/.ssh/id_rsa')),
            'connect_timeout': ssh_conf.get('connect_timeout', 10),
            'command_timeout': ssh_conf.get('command_timeout', 10)
        }
    
    def _expand_path(self, path: str) -> str:
        """경로 확장 (~/ 처리)"""
        try:
            return str(Path(path).expanduser())
        except Exception:
            return path
    
    def execute_ssh(self, host: str, ip: str, command: str, 
                    port: int = 22, timeout: int = None) -> ConnectionResult:
        """SSH로 원격 명령 실행"""
        
        if not ip or ip.lower() == 'none':
            return ConnectionResult(
                success=False, host=host, ip=ip,
                error_message="IP 주소가 설정되지 않았습니다."
            )

        start_time = datetime.now()
        timeout = timeout or self.ssh_config['command_timeout']
        
        ssh_key = self._expand_path(self.ssh_config['private_key_path'])
        user = self.ssh_config['user']
        connect_timeout = self.ssh_config['connect_timeout']
        
        # SSH 명령 구성
        ssh_cmd = [
            'ssh',
            '-q',                           # Quiet 모드
            '-n',                           # Stdin 리다이렉트
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', f'ConnectTimeout={connect_timeout}',
            '-o', 'BatchMode=yes',
            '-o', 'LogLevel=ERROR',
            '-p', str(port),
            '-i', ssh_key,
            f'{user}@{ip}',
            command
        ]
        
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return ConnectionResult(
                success=(result.returncode == 0),
                host=host,
                ip=ip,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                return_code=result.returncode,
                execution_time=execution_time,
                error_message=result.stderr.strip() if result.returncode != 0 else ""
            )
            
        except subprocess.TimeoutExpired:
            return ConnectionResult(
                success=False,
                host=host,
                ip=ip,
                error_message=f"명령 실행 타임아웃 ({timeout}s)",
                execution_time=timeout
            )
        except FileNotFoundError:
            return ConnectionResult(
                success=False,
                host=host,
                ip=ip,
                error_message="SSH 클라이언트를 찾을 수 없습니다"
            )
        except Exception as e:
            return ConnectionResult(
                success=False,
                host=host,
                ip=ip,
                error_message=str(e)
            )

    def execute_local(self, command: str, timeout: int = None) -> ConnectionResult:
        """로컬(Bastion)에서 명령 실행"""
        start_time = datetime.now()
        timeout = timeout or self.ssh_config['command_timeout']
        
        try:
            # shell=True를 사용하여 파이프(|) 등의 쉘 기능 지원
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return ConnectionResult(
                success=(result.returncode == 0),
                host="localhost",
                ip="127.0.0.1",
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                return_code=result.returncode,
                execution_time=execution_time,
                error_message=result.stderr.strip() if result.returncode != 0 else ""
            )
            
        except subprocess.TimeoutExpired:
            return ConnectionResult(
                success=False,
                host="localhost",
                ip="127.0.0.1",
                error_message=f"명령 실행 타임아웃 ({timeout}s)",
                execution_time=timeout
            )
        except Exception as e:
            return ConnectionResult(
                success=False,
                host="localhost",
                ip="127.0.0.1",
                error_message=str(e)
            )
    
    def check_tcp_port(self, ip: str, port: int, timeout: int = 5) -> bool:
        """TCP 포트 연결 확인"""
        if not ip or ip.lower() == 'none':
            return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def check_http_status(self, url: str, expected_status: int = 200, 
                          timeout: int = 10) -> Tuple[bool, int]:
        """HTTP 상태 코드 확인"""
        if not url or '://:' in url or 'none' in url.lower():
            return (False, 0)

        try:
            import urllib.request
            import urllib.error
            
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent', 'CMP-Infra-Check/1.0')
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return (response.status == expected_status, response.status)
                
        except urllib.error.HTTPError as e:
            return (e.code == expected_status, e.code)
        except Exception:
            return (False, 0)
    
    def get_all_servers(self) -> List[Dict[str, Any]]:
        """모든 서버 목록 반환"""
        servers = []
        
        # CI/CD 서버
        cicd = self.inventory.get('cicd_servers', {})
        if cicd:
            for key, server in cicd.items():
                if not server: continue
                servers.append({
                    'category': 'CI/CD',
                    'name': server.get('name', key),
                    'hostname': server.get('hostname', ''),
                    'ip': server.get('ip', ''),
                    'port': server.get('ssh_port', 22),
                    'services': server.get('services', [])
                })
        
        # 클러스터별 서버
        for cluster_key in ['dev_cluster', 'stg_cluster', 'prd_cluster']:
            cluster = self.inventory.get(cluster_key, {})
            if not cluster: continue
            
            env = cluster.get('env', cluster_key.upper())
            
            # Masters
            for master in cluster.get('masters', []):
                servers.append({
                    'category': f'{env} Master',
                    'name': master.get('name', ''),
                    'hostname': master.get('hostname', ''),
                    'ip': master.get('ip', ''),
                    'port': master.get('ssh_port', 22),
                    'cluster': cluster_key
                })
            
            # Workers
            for worker in cluster.get('workers', []):
                servers.append({
                    'category': f'{env} Worker',
                    'name': worker.get('name', ''),
                    'hostname': worker.get('hostname', ''),
                    'ip': worker.get('ip', ''),
                    'port': worker.get('ssh_port', 22),
                    'cluster': cluster_key
                })
            
            # Bastion
            bastion = cluster.get('bastion')
            if bastion:
                servers.append({
                    'category': f'{env} Bastion',
                    'name': bastion.get('name', ''),
                    'hostname': bastion.get('hostname', ''),
                    'ip': bastion.get('ip', ''),
                    'port': bastion.get('ssh_port', 22),
                    'cluster': cluster_key,
                    'services': bastion.get('services', [])
                })
            
            # Databases
            for db in cluster.get('databases', []):
                servers.append({
                    'category': f'{env} Database',
                    'name': db.get('name', ''),
                    'hostname': db.get('hostname', ''),
                    'ip': db.get('ip', ''),
                    'port': db.get('ssh_port', 22),
                    'cluster': cluster_key,
                    'services': db.get('services', [])
                })
        
        return servers
    
    def get_cluster_info(self, cluster_key: str) -> Dict[str, Any]:
        """특정 클러스터 정보 반환"""
        return self.inventory.get(cluster_key, {})
    
    def get_cicd_servers(self) -> Dict[str, Any]:
        """CI/CD 서버 정보 반환"""
        return self.inventory.get('cicd_servers', {})
    
    def mask_ip(self, ip: str) -> str:
        """IP 주소 마스킹 (보안 로깅용)"""
        if not ip: return "N/A"
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
        return "xxx.xxx.xxx.xxx"


def get_executor(demo_mode: bool = False, inventory_path: str = "config/dev-inventory.yaml"):
    """실행기 팩토리 함수"""
    return RemoteExecutor(inventory_path)