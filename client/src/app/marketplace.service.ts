// src/app/services/marketplace.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Product } from '../models/product.model';

@Injectable({
  providedIn: 'root'
})
export class MarketplaceService {
  private apiUrl = 'http://localhost:8000/api/marketplace';

  constructor(private http: HttpClient) {}

  getRecommendedProducts(): Observable<Product[]> {
    return this.http.get<Product[]>(`${this.apiUrl}/recommended/`);
  }

  getProducts(query: string = ''): Observable<Product[]> {
    return this.http.get<Product[]>(`${this.apiUrl}?q=${query}`);
  }

  getProduct(id: number): Observable<Product> {
    return this.http.get<Product>(`${this.apiUrl}/${id}/`);
  }

  createProduct(product: Product): Observable<Product> {
    return this.http.post<Product>(`${this.apiUrl}/`, product);
  }

  createProductComment(productId: number, comment: { text: string }): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/${productId}/comments/`, comment);
  }
}
