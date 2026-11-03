import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';

/** The public front page. Signed-in visitors never see it: guestGuard sends them to the feed. */
@Component({
  selector: 'app-landing',
  imports: [RouterLink, MatIconModule],
  templateUrl: './landing.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrls: ['../auth/login/login.component.scss', './landing.component.scss'],
})
export class LandingComponent {
  readonly features = [
    {
      icon: 'dynamic_feed',
      title: $localize`:@@landing.feedTitle:Feed`,
      text: $localize`:@@landing.feedText:Post updates, photos and videos, then comment on and react to what your friends share.`,
    },
    {
      icon: 'chat_bubble_outline',
      title: $localize`:@@landing.chatTitle:Chat`,
      text: $localize`:@@landing.chatText:Message one person or a whole group, with voice notes when typing is too slow.`,
    },
    {
      icon: 'group',
      title: $localize`:@@landing.groupsTitle:Groups`,
      text: $localize`:@@landing.groupsText:Join groups around what you care about, or start your own and invite people in.`,
    },
    {
      icon: 'storefront',
      title: $localize`:@@landing.marketplaceTitle:Marketplace`,
      text: $localize`:@@landing.marketplaceText:List things you want to sell, browse what others are selling and save what you like.`,
    },
    {
      icon: 'smart_display',
      title: $localize`:@@landing.videoTitle:Video`,
      text: $localize`:@@landing.videoText:Upload videos, watch what others have shared and find them again in your watch history.`,
    },
    {
      icon: 'auto_stories',
      title: $localize`:@@landing.pagesTitle:Pages`,
      text: $localize`:@@landing.pagesText:Create a page for a project or business, and follow the pages you want to hear from.`,
    },
  ];

  /** Moves focus as well as the view, so the next Tab continues from the section. */
  learnMore(section: HTMLElement): void {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    section.focus({ preventScroll: true });
    section.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  }
}
