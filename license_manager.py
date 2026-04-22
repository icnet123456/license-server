
import os
import json
import hashlib
import datetime
import uuid

import requests

DEFAULT_MASTER_KEY = "your-master-key"
LICENSE_VALIDITY_DAYS = 30
MAX_LICENSE_DAYS = 3650
DEFAULT_SERVER_BASE_URL = "https://license-server-oe3u.onrender.com"
SERVER_URL = os.getenv(
    'LICENSE_SERVER_URL',
    f"{os.getenv('LICENSE_SERVER_BASE_URL', DEFAULT_SERVER_BASE_URL).rstrip('/')}/api/check-license",
)
TRIAL_URL = os.getenv(
    'LICENSE_SERVER_TRIAL_URL',
    f"{os.getenv('LICENSE_SERVER_BASE_URL', DEFAULT_SERVER_BASE_URL).rstrip('/')}/api/start-trial",
)
CHECK_TRIAL_URL = os.getenv(
    'LICENSE_SERVER_CHECK_TRIAL_URL',
    f"{os.getenv('LICENSE_SERVER_BASE_URL', DEFAULT_SERVER_BASE_URL).rstrip('/')}/api/check-trial",
)
CHECK_DEVICE_URL = os.getenv(
    'LICENSE_SERVER_CHECK_DEVICE_URL',
    f"{os.getenv('LICENSE_SERVER_BASE_URL', DEFAULT_SERVER_BASE_URL).rstrip('/')}/api/check-device",
)
REQUEST_TIMEOUT_SECONDS = 20


def get_machine_fingerprint():
    try:
        mac = uuid.getnode()
        disk = os.getenv('SystemDrive', 'C:')
        if os.name == 'nt':
            import subprocess
            try:
                output = subprocess.check_output(f'vol {disk}', shell=True, text=True)
                serial = output.strip().split()[-1]
            except Exception:
                serial = 'unknown'
        else:
            serial = 'unknown'
        hwid = f"{mac}-{serial}"
        return hashlib.sha256(hwid.encode()).hexdigest()[:16]
    except Exception:
        return "UNKNOWN-HWID"

def _load_state(state_path):
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_state(state_path, state):
    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _today():
    return datetime.datetime.now().date()

def _date_from_str(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _parse_date_candidate(value):
    text = str(value or '').strip()
    if not text:
        return None

    for candidate in (text, text[:10]):
        parsed = _date_from_str(candidate)
        if parsed:
            return parsed

    try:
        normalized = text.replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(normalized).date()
    except Exception:
        return None


def _days_left_until(expires, today=None):
    if not expires:
        return 0
    comparison_day = today or _today()
    return max(0, (expires - comparison_day).days)


def _extract_expiry_date(payload):
    if not isinstance(payload, dict):
        return None

    for key in (
        'expires',
        'expires_at',
        'expire_date',
        'expiry_date',
        'expiration_date',
        'valid_until',
        'end_date',
    ):
        parsed = _parse_date_candidate(payload.get(key))
        if parsed:
            return parsed
    return None


def _is_active_response(payload):
    if not isinstance(payload, dict):
        return False

    status = str(payload.get('status', '') or '').strip().lower()
    if status in {'active', 'activated', 'valid', 'ok'}:
        return True

    ok_value = payload.get('ok')
    if isinstance(ok_value, bool):
        return ok_value

    return False


def _extract_license_metadata(payload):
    if not isinstance(payload, dict):
        return {}

    metadata = {}
    for source_key, target_key in (
        ('customer_name', 'customer_name'),
        ('max_devices', 'max_devices'),
        ('used_devices', 'used_devices'),
        ('status', 'server_status'),
        ('message', 'server_message'),
        ('trial_days', 'trial_days'),
        ('created_at', 'trial_created_at'),
    ):
        value = payload.get(source_key)
        if value not in (None, ''):
            metadata[target_key] = value

    expires = _extract_expiry_date(payload)
    if expires:
        metadata['expires'] = str(expires)

    return metadata


def _request_license_status(license_key, machine_fingerprint):
    payload = {
        'license_key': str(license_key or '').strip(),
        'device_id': machine_fingerprint,
    }

    try:
        response = requests.post(
            SERVER_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        return {
            'status': 'error',
            'message': f'Connection error: {exc}',
        }

    try:
        response_data = response.json()
    except ValueError:
        response_data = {}

    if not isinstance(response_data, dict):
        response_data = {'status': 'error', 'message': 'Invalid server response'}

    if not response.ok and 'status' not in response_data:
        response_data['status'] = 'error'
        response_data['message'] = response_data.get('message') or f'HTTP {response.status_code}'

    return response_data


def _request_device_status(machine_fingerprint):
    payload = {'device_id': machine_fingerprint}

    try:
        response = requests.post(
            CHECK_DEVICE_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        return {
            'status': 'error',
            'message': f'Connection error: {exc}',
        }

    try:
        response_data = response.json()
    except ValueError:
        response_data = {}

    if not isinstance(response_data, dict):
        response_data = {'status': 'error', 'message': 'Invalid server response'}

    if not response.ok and 'status' not in response_data:
        response_data['status'] = 'error'
        response_data['message'] = response_data.get('message') or f'HTTP {response.status_code}'

    return response_data


def _request_trial_status(machine_fingerprint, url=TRIAL_URL):
    payload = {'device_id': machine_fingerprint}

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        return {
            'status': 'error',
            'message': f'Connection error: {exc}',
        }

    try:
        response_data = response.json()
    except ValueError:
        response_data = {}

    if not isinstance(response_data, dict):
        response_data = {'status': 'error', 'message': 'Invalid server response'}

    if not response.ok and 'status' not in response_data:
        response_data['status'] = 'error'
        response_data['message'] = response_data.get('message') or f'HTTP {response.status_code}'

    return response_data


def check_trial(machine_fingerprint=None):
    hwid = machine_fingerprint or get_machine_fingerprint()
    result = _request_trial_status(hwid, url=CHECK_TRIAL_URL)
    status_text = str(result.get('status', '') or '').strip().lower()

    if status_text == 'error':
        return {
            'ok': False,
            'error': 'connection',
            'message': str(result.get('message', 'Connection error') or 'Connection error'),
            'response': result,
        }

    if status_text != 'trial':
        return {
            'ok': False,
            'message': str(result.get('message', 'Trial is not active') or 'Trial is not active'),
            'response': result,
        }

    expires = _extract_expiry_date(result)
    return {
        'ok': True,
        'status': 'trial',
        'machine_fingerprint': hwid,
        'expires': str(expires) if expires else '',
        'days': _days_left_until(expires) if expires else int(result.get('days_left', 0) or 0),
        'message': str(result.get('message', '') or ''),
        'response': result,
    }


def check_device_activation(machine_fingerprint=None):
    hwid = machine_fingerprint or get_machine_fingerprint()
    result = _request_device_status(hwid)
    status_text = str(result.get('status', '') or '').strip().lower()

    if status_text == 'error':
        return {
            'ok': False,
            'error': 'connection',
            'message': str(result.get('message', 'Connection error') or 'Connection error'),
            'response': result,
        }

    if not _is_active_response(result):
        return {
            'ok': False,
            'message': str(result.get('message', 'Device is not activated') or 'Device is not activated'),
            'response': result,
        }

    expires = _extract_expiry_date(result)
    return {
        'ok': True,
        'status': 'activated',
        'machine_fingerprint': hwid,
        'expires': str(expires) if expires else '',
        'days': _days_left_until(expires) if expires else 0,
        'message': str(result.get('message', '') or ''),
        'response': result,
    }


def start_trial(state_path, machine_fingerprint=None):
    hwid = machine_fingerprint or get_machine_fingerprint()
    result = _request_trial_status(hwid)
    status_text = str(result.get('status', '') or '').strip().lower()

    if status_text == 'error':
        return {'ok': False, 'error': 'connection', 'message': str(result.get('message', 'Connection error') or 'Connection error')}

    if status_text != 'trial':
        return {
            'ok': False,
            'message': str(result.get('message', 'Trial is not available') or 'Trial is not available'),
            'response': result,
        }

    expires = _extract_expiry_date(result)
    today = _today()
    state = _load_state(state_path)
    state.update({
        'created_on': str(_date_from_str(state.get('created_on')) or today),
        'last_run': str(today),
        'last_validated': datetime.datetime.now().isoformat(timespec='seconds'),
        'machine_fingerprint': hwid,
        'activated': False,
        'activation_code': '',
        'license_key': '',
        'trial_active': True,
        'trial_started': True,
        'expires': str(expires) if expires else '',
        'last_error': '',
        'online_mode': True,
    })
    state.update(_extract_license_metadata(result))
    _save_state(state_path, state)
    return {
        'ok': True,
        'status': 'trial',
        'expires_iso': str(expires) if expires else '-',
        'days_left': _days_left_until(expires, today) if expires else 0,
        'message': str(result.get('message', '') or ''),
        'response': result,
    }


def validate_activation_code(code, master_key=None, machine_fingerprint=None):
    hwid = machine_fingerprint or get_machine_fingerprint()
    normalized_code = str(code or "").strip()
    if not normalized_code:
        return {'ok': False, 'machine_fingerprint': hwid, 'message': 'License key is required'}

    result = _request_license_status(normalized_code, hwid)
    if str(result.get('status', '')).strip().lower() == 'error':
        return {
            'ok': False,
            'machine_fingerprint': hwid,
            'message': str(result.get('message', 'Connection error') or 'Connection error'),
            'error': 'connection',
            'response': result,
        }

    if _is_active_response(result):
        expires = _extract_expiry_date(result)
        return {
            'ok': True,
            'machine_fingerprint': hwid,
            'license_key': normalized_code,
            'expires': str(expires) if expires else '',
            'days': _days_left_until(expires) if expires else 0,
            'message': str(result.get('message', '') or ''),
            'response': result,
        }

    return {
        'ok': False,
        'machine_fingerprint': hwid,
        'message': str(result.get('message', 'License is not active') or 'License is not active'),
        'response': result,
    }

def ensure_license_state(state_path, master_key=None):
    hwid = get_machine_fingerprint()
    state = _load_state(state_path)
    today = _today()
    last_run = _date_from_str(state.get('last_run')) or today
    license_key = str(state.get('license_key') or state.get('activation_code') or '').strip()
    expires = _date_from_str(state.get('expires'))
    created_on = _date_from_str(state.get('created_on')) or today

    if today < last_run:
        return {
            'status': 'expired',
            'days_left': 0,
            'expires': str(expires) if expires else '-',
            'machine_fingerprint': hwid,
            'tampered': True,
            'state': state
        }

    device_validation = check_device_activation(machine_fingerprint=hwid)
    if device_validation.get('ok'):
        expires = _date_from_str(device_validation.get('expires')) or expires
        days_left = _days_left_until(expires, today) if expires else 0
        state.update({
            'created_on': str(created_on),
            'last_run': str(today),
            'last_validated': datetime.datetime.now().isoformat(timespec='seconds'),
            'machine_fingerprint': hwid,
            'activated': True,
            'trial_active': False,
            'activation_code': '',
            'license_key': '',
            'expires': str(expires) if expires else '',
            'last_error': '',
            'online_mode': True,
        })
        state.update(_extract_license_metadata(device_validation.get('response')))
        _save_state(state_path, state)
        return {
            'status': 'activated',
            'days_left': days_left,
            'expires': str(expires) if expires else '-',
            'machine_fingerprint': hwid,
            'tampered': False,
            'state': state,
        }

    if not license_key:
        trial_validation = check_trial(machine_fingerprint=hwid)
        if trial_validation.get('ok'):
            expires = _date_from_str(trial_validation.get('expires')) or expires
            state.update({
                'created_on': str(created_on),
                'last_run': str(today),
                'last_validated': datetime.datetime.now().isoformat(timespec='seconds'),
                'machine_fingerprint': hwid,
                'activated': False,
                'trial_active': True,
                'trial_started': True,
                'activation_code': '',
                'license_key': '',
                'expires': str(expires) if expires else '',
                'last_error': '',
                'online_mode': True,
            })
            state.update(_extract_license_metadata(trial_validation.get('response')))
            _save_state(state_path, state)
            return {
                'status': 'trial',
                'days_left': _days_left_until(expires, today),
                'expires': str(expires) if expires else '-',
                'machine_fingerprint': hwid,
                'tampered': False,
                'state': state,
            }

        state.update({
            'created_on': str(created_on),
            'last_run': str(today),
            'machine_fingerprint': hwid,
            'activated': False,
            'trial_active': False,
            'activation_code': '',
            'license_key': '',
            'expires': '',
            'last_error': device_validation.get('message', '') or trial_validation.get('message', ''),
            'online_mode': True,
        })
        _save_state(state_path, state)
        return {
            'status': 'expired',
            'days_left': 0,
            'expires': '-',
            'machine_fingerprint': hwid,
            'tampered': False,
            'state': state,
        }

    validation = validate_activation_code(license_key, machine_fingerprint=hwid)
    if validation.get('ok'):
        expires = _date_from_str(validation.get('expires')) or expires
        days_left = _days_left_until(expires, today) if expires else 0
        response_metadata = _extract_license_metadata(validation.get('response'))
        state.update({
            'created_on': str(created_on),
            'last_run': str(today),
            'last_validated': datetime.datetime.now().isoformat(timespec='seconds'),
            'machine_fingerprint': hwid,
            'activated': True,
            'trial_active': False,
            'activation_code': '',
            'license_key': '',
            'expires': str(expires) if expires else '',
            'last_error': '',
            'online_mode': True,
        })
        state.update(response_metadata)
        _save_state(state_path, state)
        return {
            'status': 'activated',
            'days_left': days_left,
            'expires': str(expires) if expires else '-',
            'machine_fingerprint': hwid,
            'tampered': False,
            'state': state,
        }

    state.update({
        'created_on': str(created_on),
        'last_run': str(today),
        'machine_fingerprint': hwid,
        'activated': False,
        'trial_active': False,
        'activation_code': license_key,
        'license_key': license_key,
        'expires': str(expires) if expires else ''
    })
    state['last_error'] = validation.get('message', '')
    state['online_mode'] = True
    _save_state(state_path, state)

    return {
        'status': 'expired',
        'days_left': 0,
        'expires': str(expires) if expires else '-',
        'machine_fingerprint': hwid,
        'tampered': False,
        'state': state
    }

def activate_license(state_path, code, master_key=None, machine_fingerprint=None):
    hwid = machine_fingerprint or get_machine_fingerprint()
    validation = validate_activation_code(code, machine_fingerprint=hwid)
    if validation.get('ok'):
        today = _today()
        expires = _date_from_str(validation.get('expires'))
        license_days = _days_left_until(expires, today) if expires else 0
        state = _load_state(state_path)
        response_metadata = _extract_license_metadata(validation.get('response'))
        state.update({
            'activated': True,
            'activation_code': '',
            'license_key': '',
            'license_days': license_days,
            'expires': str(expires) if expires else '',
            'last_run': str(today),
            'last_validated': datetime.datetime.now().isoformat(timespec='seconds'),
            'machine_fingerprint': hwid,
            'last_error': '',
            'online_mode': True,
        })
        state.update(response_metadata)
        if not state.get('created_on'):
            state['created_on'] = str(today)
        _save_state(state_path, state)
        return {
            'ok': True,
            'expires_iso': str(expires) if expires else '-',
            'license_days': license_days,
            'message': validation.get('message', ''),
        }
    else:
        return {
            'ok': False,
            'message': validation.get('message', 'License activation failed'),
            'error': validation.get('error'),
        }

def reveal_embedded_secret(secret):
    return secret

def update_license_metadata(state_path, metadata, master_key=None, machine_fingerprint=None):
    state = _load_state(state_path)
    state.update(metadata)
    _save_state(state_path, state)

def generate_activation_code_for_hwid(hwid, master_key=None, days=LICENSE_VALIDITY_DAYS):
    raise NotImplementedError('Online activation is enabled; generate activation keys from the server dashboard.')
