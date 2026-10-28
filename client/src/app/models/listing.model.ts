import { User } from './user.model';

export interface ListingImage {
  id: number;
  image: string;
  is_primary: boolean;
  order: number;
}

export interface ListingCategory {
  id: number;
  name: string;
  slug: string;
  icon: string;
  parent?: number | null;
  children?: ListingCategory[];
}

export type ListingCondition = 'new' | 'like_new' | 'good' | 'fair' | 'poor';
export type ListingStatus = 'active' | 'reserved' | 'sold' | 'draft';

export interface Rating {
  average: number | null;
  count: number;
}

export interface Listing {
  id: number;
  seller: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  title: string;
  description: string;
  price: string;
  currency: string;
  condition: ListingCondition;
  category: ListingCategory | null;
  location: string;
  /** Rounded to ~11 km for other users; the seller sees their own stored (~1 km) point. */
  approx_point: { latitude: number; longitude: number } | null;
  /** Whole kilometres from the point the list was filtered by, when one was given. */
  distance_km: number | null;
  status: ListingStatus;
  views_count: number;
  likes_count: number;
  images: ListingImage[];
  is_liked: boolean;
  rating: Rating;
  seller_rating: Rating;
  created_at: string;
  updated_at: string;
}

export interface ListingReview {
  id: number;
  listing: number;
  reviewer: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  rating: number;
  comment: string;
  created_at: string;
}

export interface SellerSummary {
  seller_id: number;
  rating: Rating;
  active_listings: number;
  reviews: ListingReview[];
}

export interface City {
  name: string;
  latitude: number;
  longitude: number;
}

export type MyListingCounts = Record<ListingStatus | 'all', number>;

export interface PriceSuggestion {
  low: number;
  median: number;
  high: number;
  currency: string;
  based_on: number;
}

export interface ListingDraft {
  title: string;
  description: string;
  category: Pick<ListingCategory, 'id' | 'slug' | 'name'> | null;
  condition: ListingCondition | null;
  price_suggestion: PriceSuggestion | null;
  ai_suggested: boolean;
}

export const LISTING_CONDITIONS: { value: ListingCondition; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'like_new', label: 'Like New' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'poor', label: 'Poor' },
];
