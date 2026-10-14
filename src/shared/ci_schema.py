"""CI field labels shared by server and desktop."""
FIELDS = {
    "customer": "고객사", "operational_status": "운영상태", "service_grade": "서비스 등급",
    "owner": "담당자", "service_name": "서비스명", "asset_tag": "자산번호",
    "location": "위치 / 랙", "environment": "환경", "purpose": "용도",
    "support_vendor": "유지보수 업체", "purchase_date": "도입일", "support_end": "유지보수 종료일", "notes": "메모",
}

AUTO_FIELDS = {
    "actual_hostname": "실제 hostname", "primary_ip": "대표 IP", "addresses": "전체 IP",
    "os_name": "OS 종류", "os_version": "OS 버전", "kernel": "커널", "architecture": "아키텍처",
    "manufacturer": "제조사", "hardware_model": "Hardware 모델", "serial_number": "Serial number",
    "hardware_uuid": "Hardware UUID", "virtualization": "가상화",
    "cpu_model": "CPU 모델", "logical_cpus": "보이는 논리 CPU", "allocated_cpus": "할당 vCPU (상한)",
    "smt_enabled": "Multithread (SMT/HT)", "smt_details": "SMT 판정 근거",
    "physical_cores": "보이는 물리 core", "memory_gib": "OS 메모리 GiB", "allocated_memory_gib": "할당 메모리 GiB",
    "gpu": "GPU", "uptime_seconds": "Uptime (시간:분:초)", "boot_time": "부팅 시각", "warnings": "수집 참고",
}


def display_value(key, value):
    """Format elapsed time without wrapping hours at midnight; keep storage numeric."""
    if key != "uptime_seconds": return value
    import math
    if value is None or isinstance(value, bool): return None
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or seconds < 0: return None
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (TypeError, ValueError, OverflowError):
        return None
