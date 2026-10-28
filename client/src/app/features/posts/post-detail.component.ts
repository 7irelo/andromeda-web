import { ChangeDetectionStrategy, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription, catchError, of, switchMap, throwError } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { Post } from '../../models/post.model';
import { PostCardComponent } from '../../shared/components/post-card/post-card.component';

/** A single post with its comments. Posts you can't see look exactly like posts that don't exist. */
@Component({
  selector: 'app-post-detail',
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <div class="post-detail">
      <a routerLink="/feed" class="back"><mat-icon>arrow_back</mat-icon> Back to feed</a>
      <div *ngIf="loading" class="center"><mat-spinner diameter="36"></mat-spinner></div>
      <app-post-card *ngIf="post && !loading" [post]="post" [expandComments]="true"
                     (postDeleted)="onDeleted()"></app-post-card>
      <section *ngIf="unavailable" class="card unavailable" role="status">
        <mat-icon>lock</mat-icon>
        <h1>This post isn't available</h1>
        <p class="text-secondary">It may have been deleted, or you may not have permission to see it.</p>
        <a mat-flat-button color="primary" routerLink="/feed">Go to your feed</a>
      </section>
      <section *ngIf="failed" class="card unavailable" role="alert">
        <h1>Something went wrong</h1>
        <p class="text-secondary">The post couldn't be loaded. Please try again.</p>
      </section>
    </div>
  `,
  styles: [`
    .post-detail { max-width: 640px; margin: 16px auto; padding: 0 16px; display: flex; flex-direction: column; gap: 12px; }
    .back { display: inline-flex; align-items: center; gap: 4px; color: var(--text-secondary); text-decoration: none; font-size: 14px; }
    .center { display: flex; justify-content: center; padding: 32px; }
    .unavailable {
      padding: 32px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px;
      h1 { font-size: 20px; margin: 0; }
      mat-icon { font-size: 40px; width: 40px; height: 40px; color: var(--text-muted); }
    }
  `],
})
export class PostDetailComponent implements OnInit, OnDestroy {
  post: Post | null = null;
  loading = true;
  unavailable = false;
  failed = false;
  private sub?: Subscription;

  constructor(private route: ActivatedRoute, private router: Router, private api: ApiService) {}

  ngOnInit(): void {
    this.sub = this.route.paramMap.pipe(
      switchMap((params) => {
        this.loading = true;
        this.unavailable = this.failed = false;
        this.post = null;
        const id = Number(params.get('id'));
        const request = Number.isInteger(id) && id > 0
          ? this.api.getPost(id)
          : throwError(() => new HttpErrorResponse({ status: 404 }));
        // Errors stay inside the inner stream so navigating to another post still works.
        return request.pipe(catchError((err: HttpErrorResponse) => {
          if (err.status === 404 || err.status === 403) this.unavailable = true;
          else this.failed = true;
          return of(null);
        }));
      }),
    ).subscribe((post) => {
      this.post = post;
      this.loading = false;
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  onDeleted(): void {
    this.router.navigate(['/feed']);
  }
}
