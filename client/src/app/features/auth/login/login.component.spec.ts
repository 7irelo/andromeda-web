import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { LoginComponent } from './login.component';
import { AuthService } from '../../../core/services/auth.service';

describe('LoginComponent', () => {
  let fixture: ComponentFixture<LoginComponent>;
  let auth: jasmine.SpyObj<AuthService>;
  const el = () => fixture.nativeElement as HTMLElement;

  function fill(selector: string, value: string): void {
    const input = el().querySelector<HTMLInputElement>(selector)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
  }

  function submit(): void {
    el().querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
  }

  beforeEach(() => {
    auth = jasmine.createSpyObj('AuthService', ['login', 'completeMfaLogin']);
    TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [provideRouter([]), { provide: AuthService, useValue: auth }],
    });
    fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
  });

  it('flags empty fields on submit instead of calling the API', () => {
    submit();
    expect(auth.login).not.toHaveBeenCalled();
    expect(el().querySelectorAll('.field-error').length).toBe(2);
    const username = el().querySelector('#login-username')!;
    expect(username.getAttribute('aria-invalid')).toBe('true');
    expect(username.getAttribute('aria-describedby')).toBe('login-username-error');
  });

  it('shows a server error as an alert', () => {
    auth.login.and.returnValue(throwError(() => ({ error: { detail: 'Nope' } })));
    fill('#login-username', 'thandi');
    fill('#login-password', 'secret');
    submit();
    expect(el().querySelector('[role="alert"]')?.textContent).toContain('Nope');
  });

  it('asks for a code when two-factor is required, and can start over', () => {
    auth.login.and.returnValue(of({ mfa_required: true, mfa_token: 't' }) as never);
    fill('#login-username', 'thandi');
    fill('#login-password', 'secret');
    submit();
    expect(el().querySelector('#login-code')).not.toBeNull();
    expect(el().querySelector('#login-password')).toBeNull();

    el().querySelector<HTMLButtonElement>('.link-btn')!.click();
    fixture.detectChanges();
    expect(el().querySelector('#login-password')).not.toBeNull();
  });

  it('reveals the password on request', () => {
    const input = el().querySelector<HTMLInputElement>('#login-password')!;
    expect(input.type).toBe('password');
    el().querySelector<HTMLButtonElement>('.reveal-btn')!.click();
    fixture.detectChanges();
    expect(input.type).toBe('text');
  });
});
