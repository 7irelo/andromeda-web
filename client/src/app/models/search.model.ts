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

export type SemanticType = 'posts' | 'listings' | 'groups' | 'pages' | 'videos';

export interface SemanticHit {
  type: SemanticType;
  score: number;
  matched_by: ('lexical' | 'semantic')[];
  item: Post & Listing & Group & Page & Omit<Video, 'status'>;
}

export interface SemanticSearchResponse {
  query: string;
  understood_as: { query: string; types: SemanticType[]; since_days: number | null; author: string | null } | null;
  semantic: boolean;
  results: SemanticHit[];
}

export interface AskSource {
  type: SemanticType;
  id: number;
  title: string;
  author: string;
  url: string;
}

export interface AskResponse {
  abstain: boolean;
  answer: string;
  claims: { text: string; sources: AskSource[] }[];
  sources: AskSource[];
}
