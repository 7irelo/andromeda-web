// src/app/models/product.model.ts
export interface Product {
  id?: number;
  creator: number;
  name: string;
  description: string;
  price: number;
  tags: string[];
  updated?: string;
  created?: string;
}
