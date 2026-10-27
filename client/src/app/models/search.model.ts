import { Group } from './group.model';
import { Listing } from './listing.model';
import { Page } from './page.model';
import { Post } from './post.model';
import { User } from './user.model';
import { Video } from './video.model';

export type SearchType = 'all' | 'people' | 'posts' | 'groups' | 'pages' | 'listings' | 'videos';

export interface SearchResponse {
  query: string;
  results: {
    people?: User[];
    posts?: Post[];
    groups?: Group[];
    pages?: Page[];
    listings?: Listing[];
    videos?: Video[];
  };
}
