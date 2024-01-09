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
}

export interface Listing {
  id: number;
  seller: Pick<User, 'id' | 'username' | 'full_name' | 'avatar_url'>;
  title: string;
  description: string;
  price: string;
  currency: string;
  condition: 'new' | 'like_new' | 'good' | 'fair' | 'poor';
  category: ListingCategory | null;
  location: string;
  status: 'active' | 'sold' | 'draft';
  views_count: number;
  likes_count: number;
  images: ListingImage[];
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}
