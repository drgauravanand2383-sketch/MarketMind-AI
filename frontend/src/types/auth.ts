/**
 * Mirrors `app.auth.models.*` and the new `/api/v1/auth` router exactly
 * (field-for-field — see `app/auth/models/{authentication,token,user}.py`).
 */

export interface AccessToken {
  token: string;
  token_type: string;
  subject: string;
  token_id: string;
  issued_at: string;
  expires_at: string;
}

export interface RefreshToken {
  token: string;
  subject: string;
  token_id: string;
  issued_at: string;
  expires_at: string;
}

export type UserStatus = "PENDING" | "ACTIVE" | "DISABLED" | "LOCKED";

export interface User {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  status: UserStatus;
  roles: string[];
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

export interface AuthenticationResponse {
  access_token: AccessToken;
  refresh_token: RefreshToken;
  user: User;
}
