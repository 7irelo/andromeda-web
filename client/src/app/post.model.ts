// src/app/post.model.ts

export class Post {
  id: number;
  title: string;
  content: string;
  creator: {
    id: number;
    username: string;
  };
  created_at: Date;
  updated_at: Date;

  constructor(data: any) {
    this.id = data.id;
    this.title = data.title;
    this.content = data.content;
    this.creator = data.creator;
    this.created_at = new Date(data.created_at);
    this.updated_at = new Date(data.updated_at);
  }
}
