import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { MarketplaceService } from '../../services/marketplace.service';
import { Product } from '../../models/product.model';

@Component({
  selector: 'app-product-detail',
  templateUrl: './product-detail.component.html',
  styleUrls: ['./product-detail.component.css']
})
export class ProductDetailComponent implements OnInit {
  product: Product | null = null;

  constructor(
    private route: ActivatedRoute,
    private marketplaceService: MarketplaceService
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.marketplaceService.getProduct(+id).subscribe((product) => {
        this.product = product;
      });
    }
  }
}
