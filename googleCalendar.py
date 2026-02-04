# googleCalendar.py
# Google Calendar OAuth + API Service

import os
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from connection import get_connection

JKT = ZoneInfo("Asia/Jakarta")
SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'

class GoogleCalendarService:
    def __init__(self):
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/manajemenUltah/google/callback')
    
    def _get_connection(self):
        return get_connection()
    
    # ========== TOKEN MANAGEMENT ==========
    
    def get_token_by_user(self, user_id):
        """Ambil token dari database by user_id"""
        conn = self._get_connection()
        if not conn: return None
        
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT token_data, email FROM google_oauth_tokens WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            if result:
                token_data = result['token_data']
                if isinstance(token_data, str):
                    token_data = json.loads(token_data)
                return {
                    'token': token_data,
                    'email': result['email']
                }
            return None
        except Exception as e:
            logging.error(f"[GoogleCal] Error get_token: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def save_token(self, user_id, credentials, email=None):
        """Simpan atau update token ke database"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            token_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            
            # Upsert: INSERT or UPDATE
            cursor.execute("""
                INSERT INTO google_oauth_tokens (user_id, token_data, email)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    token_data = VALUES(token_data),
                    email = VALUES(email),
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, json.dumps(token_data), email))
            
            conn.commit()
            logging.info(f"[GoogleCal] Token saved for user {user_id}, email: {email}")
            return True
        except Exception as e:
            logging.error(f"[GoogleCal] Error save_token: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def delete_token(self, user_id):
        """Hapus token dari database (disconnect)"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM google_oauth_tokens WHERE user_id = %s", (user_id,))
            conn.commit()
            logging.info(f"[GoogleCal] Token deleted for user {user_id}")
            return True
        except Exception as e:
            logging.error(f"[GoogleCal] Error delete_token: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    # ========== OAUTH FLOW ==========
    
    def create_auth_flow(self):
        """Create OAuth flow untuk redirect ke Google"""
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        return flow
    
    def get_auth_url(self):
        """Generate OAuth URL"""
        flow = self.create_auth_flow()
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh_token
        )
        return auth_url, state
    
    def handle_callback(self, authorization_response, state=None):
        """Handle OAuth callback dan return credentials + user info"""
        flow = self.create_auth_flow()
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        
        # Get user email from Google
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            
            # Build people service to get email
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            email = user_info.get('email', 'Unknown')
        except Exception as e:
            logging.warning(f"[GoogleCal] Could not get user email: {e}")
            email = None
        
        return credentials, email
    
    # ========== CALENDAR API ==========
    
    def build_service(self, user_id):
        """Build Calendar API service dari stored token"""
        token_info = self.get_token_by_user(user_id)
        if not token_info:
            return None
        
        try:
            token_data = token_info['token']
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes')
            )
            
            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
                # Update token in DB
                self.save_token(user_id, credentials, token_info['email'])
            
            service = build('calendar', 'v3', credentials=credentials)
            return service
        except Exception as e:
            logging.error(f"[GoogleCal] Error building service: {e}")
            return None
    
    def create_birthday_event(self, user_id, record, attendees=None):
        """
        Create birthday event di Google Calendar
        
        Args:
            user_id: ID user (untuk ambil token)
            record: Dict dengan keys: nama, tanggal, bulan, tahun_lahir
            attendees: List of email strings untuk share event
        
        Returns:
            event_id jika sukses, None jika gagal
        """
        service = self.build_service(user_id)
        if not service:
            return None
        
        try:
            nama = record.get('nama', 'Birthday')
            tanggal = record.get('tanggal', 1)
            bulan = record.get('bulan', 1)
            
            # Create event date (recurring yearly)
            now = datetime.now(JKT)
            event_year = now.year
            
            # Jika ultah sudah lewat tahun ini, set untuk tahun depan
            try:
                event_date = datetime(event_year, bulan, tanggal)
                if event_date < datetime.now():
                    event_year += 1
                    event_date = datetime(event_year, bulan, tanggal)
            except ValueError:
                # Invalid date (e.g., 30 Feb)
                event_date = datetime(event_year, bulan, min(tanggal, 28))
            
            # Calculate age if year is known
            tahun_lahir = record.get('tahun_lahir')
            if tahun_lahir:
                usia = event_year - tahun_lahir
                summary = f"🎂 Ultah {nama} ({usia} tahun)"
            else:
                summary = f"🎂 Ultah {nama}"
            
            event = {
                'summary': summary,
                'description': f"Ulang tahun {nama}\nNIM: {record.get('nim', '-')}\nProdi: {record.get('prodi', '-')}",
                'start': {
                    'date': event_date.strftime('%Y-%m-%d'),
                    'timeZone': 'Asia/Jakarta',
                },
                'end': {
                    'date': event_date.strftime('%Y-%m-%d'),
                    'timeZone': 'Asia/Jakarta',
                },
                'recurrence': ['RRULE:FREQ=YEARLY'],  # Recurring setiap tahun
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 1440},  # 1 day before
                        {'method': 'popup', 'minutes': 60},    # 1 hour before
                    ],
                },
            }
            
            # Add attendees jika ada
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees if email]
            
            created_event = service.events().insert(
                calendarId='primary',
                body=event,
                sendUpdates='all' if attendees else 'none'
            ).execute()
            
            logging.info(f"[GoogleCal] Event created: {created_event.get('id')} for {nama}")
            return created_event.get('id')
            
        except HttpError as e:
            logging.error(f"[GoogleCal] HTTP Error creating event: {e}")
            return None
        except Exception as e:
            logging.error(f"[GoogleCal] Error creating event: {e}")
            return None
    
    def delete_event(self, user_id, event_id):
        """Delete event dari Google Calendar"""
        service = self.build_service(user_id)
        if not service:
            return False
        
        try:
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            logging.info(f"[GoogleCal] Event deleted: {event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logging.warning(f"[GoogleCal] Event not found: {event_id}")
                return True  # Already deleted
            logging.error(f"[GoogleCal] HTTP Error deleting event: {e}")
            return False
        except Exception as e:
            logging.error(f"[GoogleCal] Error deleting event: {e}")
            return False

# Instance
google_cal_service = GoogleCalendarService()
