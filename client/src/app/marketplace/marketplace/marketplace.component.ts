import { Component, OnInit } from '@angular/core';
import { MarketplaceService } from '../../services/marketplace.service';
import { Product } from '../../models/product.model';

@Component({
  selector: 'app-marketplace',
  templateUrl: './marketplace.component.html',
  styleUrls: ['./marketplace.component.css']
})
export class MarketplaceComponent implements OnInit {
  products: Product[] = [];

  constructor(private marketplaceService: MarketplaceService) {}

  ngOnInit(): void {
    this.marketplaceService.getProducts().subscribe((products) => {
      this.products = products;
    });
  }
}
