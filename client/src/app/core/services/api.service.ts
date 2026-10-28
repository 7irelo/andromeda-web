import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Post, Comment, FeedPage, FeedSort, PostRevision } from '../../models/post.model';
import { User, FriendRequest } from '../../models/user.model';
import { CatchUp, ChatRoom, ChatUnread, Message, MessagesAfter } from '../../models/chat.model';
import { Notification, NotificationPreferences } from '../../models/notification.model';
import {
  City, Listing, ListingCategory, ListingDraft, ListingReview, ListingStatus, MyListingCounts, SellerSummary,
} from '../../models/listing.model';
import { AskResponse, SearchResponse, SearchType, SemanticSearchResponse, SemanticType } from '../../models/search.model';
import {
  Group, GroupBan, GroupInvite, GroupInvitePreview, GroupJoinRequest, GroupMember, GroupRole, GroupRule,
} from '../../models/group.model';
import { Video, VideoComment } from '../../models/video.model';
import { Page, PageRole, PageTeamMember } from '../../models/page.model';

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
  /** Home feed. Pass the previous page's `next_cursor` to continue; the window stays stable under new posts. */
  getFeed(sort: FeedSort = 'top', cursor: string | null = null): Observable<FeedPage> {
    let params = new HttpParams().set('feed', 'true').set('sort', sort);
    if (cursor) params = params.set('cursor', cursor);
    return this.http.get<FeedPage>(`${this.API}/posts/`, { params });
  }

  getPost(id: number): Observable<Post> {
    return this.http.get<Post>(`${this.API}/posts/${id}/`);
  }

  getPostRevisions(id: number): Observable<PostRevision[]> {
    return this.http.get<PostRevision[]>(`${this.API}/posts/${id}/revisions/`);
  }

  getTagPosts(tag: string, page = 1): Observable<PaginatedResponse<Post>> {
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/`, {
      params: { tag, page: page.toString() },
    });
  }

  getSavedPosts(page = 1): Observable<PaginatedResponse<Post>> {
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/saved/`, { params: { page: page.toString() } });
  }

  savePost(id: number): Observable<{ saved: boolean }> {
    return this.http.post<{ saved: boolean }>(`${this.API}/posts/${id}/save/`, {});
  }

  unsavePost(id: number): Observable<{ saved: boolean }> {
    return this.http.delete<{ saved: boolean }>(`${this.API}/posts/${id}/save/`);
  }

  hidePost(id: number): Observable<{ hidden: boolean }> {
    return this.http.post<{ hidden: boolean }>(`${this.API}/posts/${id}/hide/`, {});
  }

  unhidePost(id: number): Observable<{ hidden: boolean }> {
    return this.http.delete<{ hidden: boolean }>(`${this.API}/posts/${id}/hide/`);
  }

  getPosts(params?: Record<string, string>): Observable<PaginatedResponse<Post>> {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => (httpParams = httpParams.set(k, v)));
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/`, { params: httpParams });
  }

  createPost(data: FormData | Record<string, unknown>): Observable<Post> {
    return this.http.post<Post>(`${this.API}/posts/`, data);
  }

  /** `media_order` (ids to keep, in order) and `images` (FormData) edit a post's gallery. */
  updatePost(id: number, data: FormData | (Partial<Post> & { media_order?: number[] })): Observable<Post> {
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

  updateComment(id: number, content: string): Observable<Comment> {
    return this.http.patch<Comment>(`${this.API}/posts/comments/${id}/`, { content });
  }

  deleteComment(id: number): Observable<void> {
    return this.http.delete<void>(`${this.API}/posts/comments/${id}/`);
  }

  likeComment(id: number): Observable<{ liked: boolean; likes_count: number }> {
    return this.http.post<{ liked: boolean; likes_count: number }>(`${this.API}/posts/comments/${id}/like/`, {});
  }

  sharePost(postId: number, content: string): Observable<Post> {
    return this.http.post<Post>(`${this.API}/posts/${postId}/share/`, { content });
  }

  // ── Users ────────────────────────────────────────────────────────────
  getUser(username: string): Observable<User> {
    return this.http.get<User>(`${this.API}/auth/users/${username}/`);
  }

  searchUsers(query: string): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(`${this.API}/auth/users/`, { params: { search: query } });
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

  catchUp(roomId: number): Observable<CatchUp> {
    return this.http.post<CatchUp>(`${this.API}/chats/rooms/${roomId}/catch_up/`, {});
  }

  markRoomRead(roomId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/mark_read/`, {});
  }

  getChatRoom(roomId: number): Observable<ChatRoom> {
    return this.http.get<ChatRoom>(`${this.API}/chats/rooms/${roomId}/`);
  }

  /** Reconnect catch-up: messages newer than the last one seen, oldest first. */
  getRoomMessagesAfter(roomId: number, afterId: number): Observable<MessagesAfter> {
    return this.http.get<MessagesAfter>(`${this.API}/chats/rooms/${roomId}/messages/`, {
      params: new HttpParams().set('after_id', afterId),
    });
  }

  searchRoomMessages(roomId: number, q: string): Observable<{ query: string; results: Message[] }> {
    return this.http.get<{ query: string; results: Message[] }>(`${this.API}/chats/rooms/${roomId}/search/`, {
      params: new HttpParams().set('q', q),
    });
  }

  getChatUnread(): Observable<ChatUnread> {
    return this.http.get<ChatUnread>(`${this.API}/chats/rooms/unread/`);
  }

  getRoomPresence(roomId: number): Observable<{ online: number[] }> {
    return this.http.get<{ online: number[] }>(`${this.API}/chats/rooms/${roomId}/presence/`);
  }

  sendVoiceNote(roomId: number, audio: Blob, filename: string, replyTo?: number | null): Observable<Message> {
    const form = new FormData();
    form.append('room', String(roomId));
    form.append('message_type', 'voice');
    form.append('file', audio, filename);
    if (replyTo) form.append('reply_to', String(replyTo));
    return this.http.post<Message>(`${this.API}/chats/messages/`, form);
  }

  /** Private attachments need the auth header, so they're fetched as blobs rather than linked. */
  getMessageFile(messageId: number): Observable<Blob> {
    return this.http.get(`${this.API}/chats/messages/${messageId}/file/`, { responseType: 'blob' });
  }

  renameChatRoom(roomId: number, name: string): Observable<ChatRoom> {
    return this.http.patch<ChatRoom>(`${this.API}/chats/rooms/${roomId}/rename/`, { name });
  }

  setChatRoomAvatar(roomId: number, file: File): Observable<ChatRoom> {
    const form = new FormData();
    form.append('avatar', file);
    return this.http.post<ChatRoom>(`${this.API}/chats/rooms/${roomId}/avatar/`, form);
  }

  removeChatRoomAvatar(roomId: number): Observable<ChatRoom> {
    return this.http.delete<ChatRoom>(`${this.API}/chats/rooms/${roomId}/avatar/`);
  }

  addChatMember(roomId: number, userId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/add_member/`, { user_id: userId });
  }

  removeChatMember(roomId: number, userId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/remove_member/`, { user_id: userId });
  }

  setChatMemberRole(roomId: number, userId: number, role: 'admin' | 'member'): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/set_role/`, { user_id: userId, role });
  }

  leaveChatRoom(roomId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/chats/rooms/${roomId}/leave/`, {});
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

  getNotificationPreferences(): Observable<NotificationPreferences> {
    return this.http.get<NotificationPreferences>(`${this.API}/notifications/preferences/`);
  }

  updateNotificationPreferences(data: {
    categories?: Record<string, Partial<{ in_app: boolean; push: boolean; email: boolean }>>;
    email_digest?: 'off' | 'daily';
    listing_digest?: boolean;
  }): Observable<NotificationPreferences> {
    return this.http.patch<NotificationPreferences>(`${this.API}/notifications/preferences/`, data);
  }

  getPushPublicKey(): Observable<{ public_key: string | null }> {
    return this.http.get<{ public_key: string | null }>(`${this.API}/notifications/push/`);
  }

  savePushSubscription(sub: PushSubscriptionJSON): Observable<unknown> {
    return this.http.post(`${this.API}/notifications/push/`, sub);
  }

  deletePushSubscription(endpoint: string): Observable<unknown> {
    return this.http.delete(`${this.API}/notifications/push/`, { body: { endpoint } });
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
    return this.http
      .get<PaginatedResponse<GroupMember>>(`${this.API}/groups/${id}/members/`)
      .pipe(map((res) => res.results));
  }

  getGroupJoinRequests(id: number): Observable<GroupJoinRequest[]> {
    return this.http.get<GroupJoinRequest[]>(`${this.API}/groups/${id}/join_requests/`);
  }

  decideGroupJoinRequest(groupId: number, requestId: number, decision: 'approve' | 'decline'): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/join_requests/${requestId}/${decision}/`, {});
  }

  updateGroup(id: number, data: FormData | Partial<Pick<Group, 'name' | 'description' | 'privacy'>>): Observable<Group> {
    return this.http.patch<Group>(`${this.API}/groups/${id}/`, data);
  }

  deleteGroup(id: number): Observable<void> {
    return this.http.delete<void>(`${this.API}/groups/${id}/`);
  }

  getGroupRules(id: number): Observable<GroupRule[]> {
    return this.http.get<GroupRule[]>(`${this.API}/groups/${id}/rules/`);
  }

  setGroupRules(id: number, rules: Pick<GroupRule, 'title' | 'description'>[]): Observable<GroupRule[]> {
    return this.http.post<GroupRule[]>(`${this.API}/groups/${id}/rules/`, { rules });
  }

  getGroupPinnedPosts(id: number): Observable<Post[]> {
    return this.http.get<Post[]>(`${this.API}/groups/${id}/pinned/`);
  }

  pinGroupPost(groupId: number, postId: number, pin: boolean): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/${pin ? 'pin' : 'unpin'}/`, { post_id: postId });
  }

  removeGroupPost(groupId: number, postId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/remove_post/`, { post_id: postId });
  }

  setGroupRole(groupId: number, userId: number, role: GroupRole): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/set_role/`, { user_id: userId, role });
  }

  removeGroupMember(groupId: number, userId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/remove_member/`, { user_id: userId });
  }

  getGroupBans(id: number): Observable<GroupBan[]> {
    return this.http
      .get<PaginatedResponse<GroupBan>>(`${this.API}/groups/${id}/bans/`)
      .pipe(map((res) => res.results));
  }

  banGroupMember(groupId: number, userId: number, reason = ''): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/ban/`, { user_id: userId, reason });
  }

  unbanGroupMember(groupId: number, userId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/unban/`, { user_id: userId });
  }

  getGroupInvites(id: number): Observable<GroupInvite[]> {
    return this.http.get<GroupInvite[]>(`${this.API}/groups/${id}/invites/`);
  }

  createGroupInvite(id: number, data: { expires_in_hours: number; max_uses?: number | null }): Observable<GroupInvite> {
    return this.http.post<GroupInvite>(`${this.API}/groups/${id}/invites/`, data);
  }

  revokeGroupInvite(groupId: number, inviteId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/groups/${groupId}/invites/${inviteId}/revoke/`, {});
  }

  previewGroupInvite(token: string): Observable<GroupInvitePreview> {
    return this.http.get<GroupInvitePreview>(`${this.API}/groups/invites/${encodeURIComponent(token)}/`);
  }

  acceptGroupInvite(token: string): Observable<{ status: string; group_id: number }> {
    return this.http.post<{ status: string; group_id: number }>(
      `${this.API}/groups/invites/${encodeURIComponent(token)}/`, {}
    );
  }

  // ── Search ─────────────────────────────────────────────────────────────────
  search(q: string, type: SearchType = 'all'): Observable<SearchResponse> {
    return this.http.get<SearchResponse>(`${this.API}/search/`, { params: { q, type } });
  }

  semanticSearch(q: string, type: SemanticType | 'all' = 'all'): Observable<SemanticSearchResponse> {
    return this.http.get<SemanticSearchResponse>(`${this.API}/search/semantic/`, { params: { q, type } });
  }

  ask(question: string): Observable<AskResponse> {
    return this.http.post<AskResponse>(`${this.API}/ask/`, { question });
  }

  // ── Profile ────────────────────────────────────────────────────────────────
  updateProfile(data: FormData | Partial<User>): Observable<User> {
    return this.http.patch<User>(`${this.API}/auth/me/`, data);
  }

  // ── Relationships ──────────────────────────────────────────────────────────
  unfriend(userId: number): Observable<{ is_friend: boolean }> {
    return this.http.delete<{ is_friend: boolean }>(`${this.API}/auth/users/${userId}/friend/`);
  }

  getFriends(userId: number, page = 1): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(`${this.API}/auth/users/${userId}/friends/`, {
      params: { page: page.toString() },
    });
  }

  blockUser(userId: number): Observable<{ blocked: boolean }> {
    return this.http.post<{ blocked: boolean }>(`${this.API}/auth/users/${userId}/block/`, {});
  }

  unblockUser(userId: number): Observable<{ blocked: boolean }> {
    return this.http.delete<{ blocked: boolean }>(`${this.API}/auth/users/${userId}/block/`);
  }

  getBlockedUsers(): Observable<User[]> {
    return this.http.get<User[]>(`${this.API}/auth/users/blocked/`);
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

  updateListing(id: number, data: Partial<Listing> | Record<string, unknown>): Observable<Listing> {
    return this.http.patch<Listing>(`${this.API}/marketplace/listings/${id}/`, data);
  }

  setListingStatus(id: number, status: ListingStatus): Observable<Listing> {
    return this.http.patch<Listing>(`${this.API}/marketplace/listings/${id}/`, { status });
  }

  getMyListings(status?: ListingStatus, page = 1): Observable<PaginatedResponse<Listing>> {
    let params = new HttpParams().set('mine', 'true').set('page', page);
    if (status) params = params.set('status', status);
    return this.http.get<PaginatedResponse<Listing>>(`${this.API}/marketplace/listings/`, { params });
  }

  getMyListingCounts(): Observable<MyListingCounts> {
    return this.http.get<MyListingCounts>(`${this.API}/marketplace/listings/mine/counts/`);
  }

  getSavedListings(page = 1): Observable<PaginatedResponse<Listing>> {
    return this.http.get<PaginatedResponse<Listing>>(`${this.API}/marketplace/listings/saved/`, {
      params: new HttpParams().set('page', page),
    });
  }

  getListingReviews(id: number): Observable<ListingReview[]> {
    return this.http.get<ListingReview[]>(`${this.API}/marketplace/listings/${id}/reviews/`);
  }

  reviewListing(id: number, data: { rating: number; comment?: string }): Observable<ListingReview> {
    return this.http.post<ListingReview>(`${this.API}/marketplace/listings/${id}/reviews/`, data);
  }

  getSeller(userId: number): Observable<SellerSummary> {
    return this.http.get<SellerSummary>(`${this.API}/marketplace/sellers/${userId}/`);
  }

  getMarketplaceCities(): Observable<City[]> {
    return this.http.get<City[]>(`${this.API}/marketplace/cities/`);
  }

  /** Listing Assistant: photos (and an optional note) in, an AI-suggested draft out. Nothing is saved. */
  draftListing(formData: FormData): Observable<ListingDraft> {
    return this.http.post<ListingDraft>(`${this.API}/marketplace/listings/draft/`, formData);
  }

  deleteListing(id: number): Observable<void> {
    return this.http.delete<void>(`${this.API}/marketplace/listings/${id}/`);
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

  getPage(id: number): Observable<Page> {
    return this.http.get<Page>(`${this.API}/pages/${id}/`);
  }

  updatePage(id: number, data: FormData | Partial<Page>): Observable<Page> {
    return this.http.patch<Page>(`${this.API}/pages/${id}/`, data);
  }

  deletePage(id: number): Observable<void> {
    return this.http.delete<void>(`${this.API}/pages/${id}/`);
  }

  getPagePosts(id: number, page = 1): Observable<PaginatedResponse<Post>> {
    return this.http.get<PaginatedResponse<Post>>(`${this.API}/posts/`, {
      params: { page_id: id.toString(), page: page.toString() },
    });
  }

  getPageFollowers(id: number, page = 1): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(`${this.API}/pages/${id}/followers/`, {
      params: { page: page.toString() },
    });
  }

  getPageTeam(id: number): Observable<PageTeamMember[]> {
    return this.http.get<PageTeamMember[]>(`${this.API}/pages/${id}/admins/`);
  }

  setPageRole(id: number, userId: number, role: PageRole): Observable<PageTeamMember> {
    return this.http.post<PageTeamMember>(`${this.API}/pages/${id}/admins/`, { user_id: userId, role });
  }

  removePageRole(id: number, userId: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.API}/pages/${id}/admins/remove/`, { user_id: userId });
  }
}
