import { TestBed } from '@angular/core/testing';
import { EmptyStateComponent } from './empty-state.component';
import { ErrorStateComponent } from './error-state.component';
import { SkeletonComponent } from './skeleton.component';

describe('State components', () => {
  it('EmptyState shows its title and message', () => {
    const fixture = TestBed.createComponent(EmptyStateComponent);
    fixture.componentRef.setInput('title', 'No groups yet');
    fixture.componentRef.setInput('message', 'Join one to see it here.');
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('h3')?.textContent).toContain('No groups yet');
    expect(el.textContent).toContain('Join one to see it here.');
  });

  it('ErrorState is an alert and emits retry', () => {
    const fixture = TestBed.createComponent(ErrorStateComponent);
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('[role="alert"]')).not.toBeNull();
    expect(el.textContent).toContain('Something went wrong');
    (el.querySelector('button') as HTMLButtonElement).click();
    expect(retried).toBe(1);
  });

  it('Skeleton renders the requested number of placeholders and announces loading once', () => {
    const fixture = TestBed.createComponent(SkeletonComponent);
    fixture.componentRef.setInput('variant', 'post');
    fixture.componentRef.setInput('count', 4);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.getAttribute('role')).toBe('status');
    expect(el.querySelectorAll('.sk-card').length).toBe(4);
    expect(el.querySelectorAll('[aria-hidden="true"]').length).toBe(4);
    expect(el.querySelector('.visually-hidden')?.textContent).toContain('Loading');
  });
});
