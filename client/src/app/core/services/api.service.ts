import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Post, Comment } from '../../models/post.model';
import { User, FriendRequest } from '../../models/user.model';
import { ChatRoom, Message } from '../../models/chat.model';
import { Notification } from '../../models/notification.model';
import { Listing, ListingCategory } from '../../models/listing.model';
import { Group, GroupMember } from '../../models/group.model';
import { Video, VideoComment } from '../../models/video.model';
import { Page } from '../../models/page.model';

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly API = environment.apiUrl;

  constructor(private http: HttpClient) {}

  // ── Posts ────────────────────────────────────────────────────────────
  getFeed(page = 1): Observable<PaginatedResponse<Post>> {
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/?feed=true&page=${page}`);
  }

  getPosts(params?: Record<string, string>): Observable<PaginatedResponse<Post>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/`, { params: httpParams });
  }

  createPost(data: FormData | Record<string, unknown>): Observable<Post> {
    return this.http.post<Post>(`${this.API}/posts/`, data);
  }

  updatePost(id: number, data: Partial<Post>): Observable<Post> {
    return this.http.patch<Post>(`${this.API}/posts/${id}/`, data);
  }

  deletePost(id: number): Observable<void> {
    return this.http.delete<void>(`${this.API}/posts/${id}/`);
  }

  reactToPost(postId: number, reaction: string): Observable<{ reacted: boolean; reaction?: string }> {
    return this.http.post<{ reacted: boolean; reaction?: string }>(
      `${this.API}/posts/${postId}/react/`, { reaction }
    );
  }

  getComments(postId: number): Observable<Comment[]> {
    return this.http.get<Comment[]>(`${this.API}/posts/${postId}/comments/`);
  }

  createComment(postId: number, data: { content: string; parent?: number }): Observable<Comment> {
    return this.http.post<Comment>(`${this.API}/posts/${postId}/comments/`, data);
  }

  sharePost(postId: number, content: string): Observable<Post> {
    return this.http.post<Post>(`${this.API}/posts/${postId}/share/`, { content });
  }

  // ── Users ────────────────────────────────────────────────────────────
  getUser(username: string): Observable<User> {
    return this.http.get<User>(`${this.API}/auth/users/${username}/`);
  }

  searchUsers(query: string): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(`${this.API}/auth/users/?search=${query}`);
  }

  getSuggestions(): Observable<User[]> {
    return this.http.get<User[]>(`${this.API}/auth/users/suggestions/`);
  }

  getFriendRequests(): Observable<PaginatedResponse<FriendRequest>> {
    return this.http.get<PaginatedResponse<FriendRequest>>(`${this.API}/auth/friend-requests/`);
  }

  getReceivedFriendRequests(): Observable<FriendRequest[]> {
    return this.http.get<FriendRequest[]>(`${this.API}/auth/friend-requests/received/`);
  }

  getSentFriendRequests(): Observable<FriendRequest[]> {
    return this.http.get<FriendRequest[]>(`${this.API}/auth/friend-requests/sent/`);
  }

  sendFriendRequest(receiverId: number): Observable<FriendRequest> {
    return this.http.post<FriendRequest>(`${this.API}/auth/friend-requests/`, { receiver_id: receiverId });
  }

  acceptFriendRequest(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/auth/friend-requests/${id}/accept/`, {});
  }

  declineFriendRequest(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/auth/friend-requests/${id}/decline/`, {});
  }

  cancelFriendRequest(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/auth/friend-requests/${id}/cancel/`, {});
  }

  // ── Chats ────────────────────────────────────────────────────────────
  getChatRooms(): Observable<PaginatedResponse<ChatRoom>> {
    return this.http.get<PaginatedResponse<ChatRoom>>(`${this.API}/chats/rooms/`);
  }

  createChatRoom(data: { member_ids: number[]; room_type?: string; name?: string }): Observable<ChatRoom> {
    return this.http.post<ChatRoom>(`${this.API}/chats/rooms/`, data);
  }

  getRoomMessages(roomId: number, page = 1): Observable<PaginatedResponse<Message>> {
    return this.http.get<PaginatedResponse<Message>>(
      `${this.API}/chats/rooms/${roomId}/messages/?page=${page}`
    );
  }

  markRoomRead(roomId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/mark_read/`, {});
  }

  // ── Notifications ─────────────────────────────────────────────────────
  getNotifications(unread = false): Observable<PaginatedResponse<Notification>> {
    const q = unread ? '?unread=true' : '';
    return this.http.get<PaginatedResponse<Notification>>(`${this.API}/notifications/${q}`);
  }

  getUnreadCount(): Observable<{ unread_count: number }> {
    return this.http.get<{ unread_count: number }>(`${this.API}/notifications/unread-count/`);
  }

  markNotificationRead(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/notifications/${id}/read/`, {});
  }

  markAllNotificationsRead(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/notifications/mark-all-read/`, {});
  }

  // ── Groups ───────────────────────────────────────────────────────────
  getGroups(params?: Record<string, string>): Observable<PaginatedResponse<Group>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Group>>(`${this.API}/groups/`, { params: httpParams });
  }

  getGroup(id: number): Observable<Group> {
    return this.http.get<Group>(`${this.API}/groups/${id}/`);
  }

  createGroup(data: { name: string; description?: string; privacy: string }): Observable<Group> {
    return this.http.post<Group>(`${this.API}/groups/`, data);
  }

  joinGroup(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${id}/join/`, {});
  }

  leaveGroup(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${id}/leave/`, {});
  }

  getGroupMembers(id: number): Observable<GroupMember[]> {
    return this.http.get<GroupMember[]>(`${this.API}/groups/${id}/members/`);
  }

  // ── Profile ────────────────────────────────────────────────────────────────
  updateProfile(data: FormData | Partial<User>): Observable<User> {
    return this.http.patch<User>(`${this.API}/auth/me/`, data);
  }

  deleteAccount(refresh: string): Observable<void> {
    return this.http.delete<void>(`${this.API}/auth/me/`, { body: { refresh } });
  }

  // ── Marketplace ───────────────────────────────────────────────────────
  getListings(params?: Record<string, string>): Observable<PaginatedResponse<Listing>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Listing>>(`${this.API}/marketplace/listings/`, { params: httpParams });
  }

  getListing(id: number): Observable<Listing> {
    return this.http.get<Listing>(`${this.API}/marketplace/listings/${id}/`);
  }

  createListing(data: FormData | Record<string, unknown>): Observable<Listing> {
    return this.http.post<Listing>(`${this.API}/marketplace/listings/`, data);
  }

  uploadListingImages(listingId: number, formData: FormData): Observable<unknown> {
    return this.http.post(`${this.API}/marketplace/listings/${listingId}/upload_images/`, formData);
  }

  likeListing(id: number): Observable<{ liked: boolean }> {
    return this.http.post<{ liked: boolean }>(`${this.API}/marketplace/listings/${id}/like/`, {});
  }

  getCategories(): Observable<ListingCategory[]> {
    return this.http.get<ListingCategory[]>(`${this.API}/marketplace/categories/`);
  }

  // ── Watch ──────────────────────────────────────────────────────────────
  getVideos(params?: Record<string, string>): Observable<PaginatedResponse<Video>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Video>>(`${this.API}/watch/videos/`, { params: httpParams });
  }

  getVideo(id: number): Observable<Video> {
    return this.http.get<Video>(`${this.API}/watch/videos/${id}/`);
  }

  uploadVideo(formData: FormData): Observable<Video> {
    return this.http.post<Video>(`${this.API}/watch/videos/`, formData);
  }

  likeVideo(id: number): Observable<{ liked: boolean }> {
    return this.http.post<{ liked: boolean }>(`${this.API}/watch/videos/${id}/like/`, {});
  }

  getVideoComments(id: number): Observable<VideoComment[]> {
    return this.http.get<VideoComment[]>(`${this.API}/watch/videos/${id}/comments/`);
  }

  createVideoComment(id: number, data: { content: string }): Observable<VideoComment> {
    return this.http.post<VideoComment>(`${this.API}/watch/videos/${id}/comments/`, data);
  }

  // ── Pages ──────────────────────────────────────────────────────────────
  getPages(params?: Record<string, string>): Observable<PaginatedResponse<Page>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Page>>(`${this.API}/pages/`, { params: httpParams });
  }

  createPage(data: { name: string; description?: string; category?: string }): Observable<Page> {
    return this.http.post<Page>(`${this.API}/pages/`, data);
  }

  followPage(id: number): Observable<{ following: boolean }> {
    return this.http.post<{ following: boolean }>(`${this.API}/pages/${id}/follow/`, {});
  }

  unfollowPage(id: number): Observable<{ following: boolean }> {
    return this.http.post<{ following: boolean }>(`${this.API}/pages/${id}/unfollow/`, {});
  }
}
