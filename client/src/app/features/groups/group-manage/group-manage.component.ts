import { Component, EventEmitter, Input, OnInit, Output, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../../core/services/api.service';
import { Group, GroupBan, GroupInvite, GroupRule } from '../../../models/group.model';

/**
 * Admin and moderator tools for a group. The server enforces every rule; this
 * only hides controls the signed-in user can't use (moderators see invites).
 */
@Component({
    selector: 'app-group-manage',
    imports: [
        CommonModule, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
        MatInputModule, MatSelectModule, MatSnackBarModule,
    ],
    template: `
    <!-- Settings (admins) -->
    <div class="card section" *ngIf="isAdmin" [formGroup]="settingsForm">
      <h3>Settings</h3>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Name</mat-label>
        <input matInput formControlName="name" maxlength="255" />
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Description</mat-label>
        <textarea matInput formControlName="description" rows="3" maxlength="5000"></textarea>
      </mat-form-field>
      <mat-form-field appearance="outline" class="w-full">
        <mat-label>Privacy</mat-label>
        <mat-select formControlName="privacy">
          <mat-option value="public">Public</mat-option>
          <mat-option value="private">Private</mat-option>
          <mat-option value="secret">Secret</mat-option>
        </mat-select>
      </mat-form-field>
      <div class="cover-row">
        <img [src]="coverPreview || group.cover_photo || 'assets/default-cover.png'" alt="Cover preview" />
        <button mat-stroked-button type="button" (click)="coverInput.click()"><mat-icon>image</mat-icon> Change cover</button>
        <input #coverInput type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden (change)="onCover($event)" />
      </div>
      <div class="row-actions">
        <button mat-flat-button color="primary" (click)="saveSettings()" [disabled]="saving || settingsForm.invalid">
          {{ saving ? 'Saving...' : 'Save settings' }}
        </button>
      </div>
    </div>

    <!-- Rules (admins) -->
    <div class="card section" *ngIf="isAdmin">
      <h3>Rules</h3>
      <div [formGroup]="rulesForm">
        <div formArrayName="rules">
          <div class="rule-row" *ngFor="let r of rulesArray.controls; let i = index" [formGroupName]="i">
            <span class="rule-num">{{ i + 1 }}</span>
            <div class="rule-fields">
              <mat-form-field appearance="outline" class="w-full">
                <mat-label>Title</mat-label>
                <input matInput formControlName="title" maxlength="120" />
              </mat-form-field>
              <mat-form-field appearance="outline" class="w-full">
                <mat-label>Details (optional)</mat-label>
                <textarea matInput formControlName="description" rows="2" maxlength="1000"></textarea>
              </mat-form-field>
            </div>
            <div class="rule-buttons">
              <button mat-icon-button (click)="moveRule(i, -1)" [disabled]="i === 0" aria-label="Move up"><mat-icon>arrow_upward</mat-icon></button>
              <button mat-icon-button (click)="moveRule(i, 1)" [disabled]="i === rulesArray.length - 1" aria-label="Move down"><mat-icon>arrow_downward</mat-icon></button>
              <button mat-icon-button (click)="rulesArray.removeAt(i)" aria-label="Delete rule"><mat-icon>delete</mat-icon></button>
            </div>
          </div>
        </div>
      </div>
      <div class="row-actions">
        <button mat-stroked-button (click)="addRule()" [disabled]="rulesArray.length >= 20"><mat-icon>add</mat-icon> Add rule</button>
        <button mat-flat-button color="primary" (click)="saveRules()" [disabled]="rulesForm.invalid">Save rules</button>
      </div>
    </div>

    <!-- Invite links (admins and moderators) -->
    <div class="card section" [formGroup]="inviteForm">
      <h3>Invite links</h3>
      <p class="text-secondary text-sm">Anyone with a link can join, even a private or secret group, until it expires or you revoke it.</p>
      <div class="invite-form">
        <mat-form-field appearance="outline">
          <mat-label>Expires after</mat-label>
          <mat-select formControlName="expires_in_hours">
            <mat-option [value]="1">1 hour</mat-option>
            <mat-option [value]="24">1 day</mat-option>
            <mat-option [value]="168">7 days</mat-option>
            <mat-option [value]="720">30 days</mat-option>
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Max uses (optional)</mat-label>
          <input matInput type="number" min="1" max="1000" formControlName="max_uses" />
        </mat-form-field>
        <button mat-flat-button color="primary" (click)="createInvite()" [disabled]="inviteForm.invalid">Create link</button>
      </div>
      <div class="new-link" *ngIf="newLink">
        <mat-icon>link</mat-icon>
        <input class="link-input" [value]="newLink" readonly (focus)="$any($event.target).select()" />
        <button mat-stroked-button (click)="copy(newLink)">Copy</button>
      </div>
      <p class="text-secondary text-xs" *ngIf="newLink">Copy it now: for security the link can't be shown again.</p>
      <div class="invite-row" *ngFor="let inv of invites">
        <div class="invite-info">
          <span class="text-sm">
            {{ inv.is_usable ? 'Active' : (inv.revoked_at ? 'Revoked' : 'Expired') }}
            · used {{ inv.uses_count }}{{ inv.max_uses ? ' / ' + inv.max_uses : '' }}
          </span>
          <span class="text-xs text-secondary">Expires {{ inv.expires_at | date: 'medium' }} · by {{ inv.created_by?.full_name || 'unknown' }}</span>
        </div>
        <button mat-stroked-button color="warn" *ngIf="inv.is_usable" (click)="revoke(inv)">Revoke</button>
      </div>
    </div>

    <!-- Bans (admins) -->
    <div class="card section" *ngIf="isAdmin">
      <h3>Banned users</h3>
      <p class="text-secondary" *ngIf="bans.length === 0">Nobody is banned.</p>
      <div class="invite-row" *ngFor="let b of bans">
        <div class="invite-info">
          <span class="text-sm font-semibold">{{ b.user.full_name }}</span>
          <span class="text-xs text-secondary">{{ b.reason || 'No reason given' }} · {{ b.created_at | date }}</span>
        </div>
        <button mat-stroked-button (click)="unban(b)">Unban</button>
      </div>
    </div>

    <div class="card section danger" *ngIf="isAdmin">
      <h3>Delete group</h3>
      <p class="text-secondary text-sm">This removes the group for everyone and can't be undone.</p>
      <div class="row-actions">
        <button mat-flat-button color="warn" (click)="deleteGroup()">Delete group</button>
      </div>
    </div>
  `,
    changeDetection: ChangeDetectionStrategy.Eager,
    styles: [`
    :host { display: flex; flex-direction: column; gap: 16px; }
    .section { padding: 16px 20px; }
    .section h3 { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
    .w-full { width: 100%; }
    .row-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
    .cover-row { display: flex; align-items: center; gap: 12px; }
    .cover-row img { width: 160px; height: 60px; object-fit: cover; border-radius: 8px; }
    .rule-row { display: flex; gap: 8px; align-items: flex-start; }
    .rule-num { font-weight: 700; padding-top: 16px; min-width: 18px; }
    .rule-fields { flex: 1; }
    .rule-buttons { display: flex; flex-direction: column; }
    .invite-form { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; margin-top: 8px; }
    .new-link { display: flex; align-items: center; gap: 8px; margin: 8px 0 4px; }
    .link-input {
      flex: 1; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface); color: inherit; font-family: monospace; font-size: 12px;
    }
    .invite-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 0; border-top: 1px solid var(--border); }
    .invite-info { display: flex; flex-direction: column; }
  `]
})
export class GroupManageComponent implements OnInit {
  @Input({ required: true }) group!: Group;
  @Input() isAdmin = false;
  @Output() groupChange = new EventEmitter<Group>();
  @Output() rulesChange = new EventEmitter<GroupRule[]>();
  @Output() deleted = new EventEmitter<void>();

  settingsForm!: FormGroup;
  rulesForm!: FormGroup;
  inviteForm!: FormGroup;
  coverFile: File | null = null;
  coverPreview: string | null = null;
  saving = false;
  invites: GroupInvite[] = [];
  bans: GroupBan[] = [];
  newLink: string | null = null;

  constructor(private apiService: ApiService, private fb: FormBuilder, private snackBar: MatSnackBar) {}

  get rulesArray(): FormArray {
    return this.rulesForm.get('rules') as FormArray;
  }

  ngOnInit(): void {
    this.settingsForm = this.fb.group({
      name: [this.group.name, [Validators.required, Validators.maxLength(255)]],
      description: [this.group.description, Validators.maxLength(5000)],
      privacy: [this.group.privacy, Validators.required],
    });
    this.rulesForm = this.fb.group({ rules: this.fb.array([]) });
    this.inviteForm = this.fb.group({
      expires_in_hours: [168, Validators.required],
      max_uses: [null, [Validators.min(1), Validators.max(1000)]],
    });
    this.loadInvites();
    if (this.isAdmin) {
      this.apiService.getGroupRules(this.group.id).subscribe({
        next: (rules) => rules.forEach((r) => this.addRule(r)),
      });
      this.loadBans();
    }
  }

  onCover(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.coverFile = file;
    const reader = new FileReader();
    reader.onload = () => (this.coverPreview = reader.result as string);
    reader.readAsDataURL(file);
  }

  saveSettings(): void {
    if (this.settingsForm.invalid || this.saving) return;
    this.saving = true;
    const data = new FormData();
    Object.entries(this.settingsForm.value).forEach(([k, v]) => data.append(k, String(v ?? '')));
    if (this.coverFile) data.append('cover_photo', this.coverFile);
    this.apiService.updateGroup(this.group.id, data).subscribe({
      next: (g) => {
        this.saving = false;
        this.coverFile = null;
        this.groupChange.emit(g);
        this.toast('Settings saved');
      },
      error: (err) => {
        this.saving = false;
        this.toast(this.firstError(err) ?? 'Could not save the settings');
      },
    });
  }

  addRule(rule?: GroupRule): void {
    this.rulesArray.push(this.fb.group({
      title: [rule?.title ?? '', [Validators.required, Validators.maxLength(120)]],
      description: [rule?.description ?? '', Validators.maxLength(1000)],
    }));
  }

  moveRule(index: number, delta: number): void {
    const control = this.rulesArray.at(index);
    this.rulesArray.removeAt(index);
    this.rulesArray.insert(index + delta, control);
  }

  saveRules(): void {
    if (this.rulesForm.invalid) return;
    this.apiService.setGroupRules(this.group.id, this.rulesArray.value).subscribe({
      next: (rules) => {
        this.rulesChange.emit(rules);
        this.toast('Rules saved');
      },
      error: () => this.toast('Could not save the rules'),
    });
  }

  loadInvites(): void {
    this.apiService.getGroupInvites(this.group.id).subscribe({ next: (invites) => (this.invites = invites) });
  }

  createInvite(): void {
    const { expires_in_hours, max_uses } = this.inviteForm.value;
    this.apiService.createGroupInvite(this.group.id, { expires_in_hours, max_uses: max_uses || null }).subscribe({
      next: (invite) => {
        this.newLink = `${window.location.origin}/groups/join/${invite.token}`;
        delete invite.token;
        this.invites = [invite, ...this.invites];
      },
      error: (err) => this.toast(err?.error?.detail ?? 'Could not create the link'),
    });
  }

  revoke(invite: GroupInvite): void {
    this.apiService.revokeGroupInvite(this.group.id, invite.id).subscribe({
      next: () => {
        invite.is_usable = false;
        invite.revoked_at = new Date().toISOString();
      },
      error: () => this.toast('Could not revoke the link'),
    });
  }

  copy(text: string): void {
    navigator.clipboard?.writeText(text).then(
      () => this.toast('Link copied'),
      () => this.toast('Copy failed: select the link and copy it manually'),
    );
  }

  loadBans(): void {
    this.apiService.getGroupBans(this.group.id).subscribe({ next: (bans) => (this.bans = bans) });
  }

  unban(ban: GroupBan): void {
    this.apiService.unbanGroupMember(this.group.id, ban.user.id).subscribe({
      next: () => (this.bans = this.bans.filter((b) => b.id !== ban.id)),
      error: () => this.toast('Could not unban this user'),
    });
  }

  deleteGroup(): void {
    if (!confirm(`Delete ${this.group.name}? This can't be undone.`)) return;
    this.apiService.deleteGroup(this.group.id).subscribe({
      next: () => this.deleted.emit(),
      error: () => this.toast('Could not delete the group'),
    });
  }

  private firstError(err: { error?: Record<string, unknown> }): string | null {
    const body = err?.error;
    if (!body || typeof body !== 'object') return null;
    const first = Object.values(body)[0];
    return Array.isArray(first) ? String(first[0]) : typeof first === 'string' ? first : null;
  }

  private toast(message: string): void {
    this.snackBar.open(message, 'Dismiss', { duration: 3000 });
  }
}
