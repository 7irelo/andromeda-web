export class Post {
  id: number;
  creator: number;
  content: string;
  tags: string[];
  participants: number[];
  likes: number[];
  updated: string;
  created: string;

  constructor(data: any) {
    this.id = data.id;
    this.creator = data.creator;
    this.content = data.content;
    this.tags = data.tags || [];
    this.participants = data.participants || [];
    this.likes = data.likes || [];
    this.updated = data.updated;
    this.created = data.created;
  }
}
