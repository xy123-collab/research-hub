"""受控内容删除。

删除帖子时必须同步清理其附件与从属记录，但不得扩大到作者在别处留下的评论。
路由删除与账号注销的“可选删除本人帖子”共用此逻辑。
"""
from sqlalchemy.orm import Session

from ..core.storage import storage
from ..models.community import (
    Post, PostAttachment, PostVariable, PostTag, PostReaction, PostComment,
    PostCommentReaction, PostFollow, PostAdminFlag,
)
from ..models.extras import ContentScope
from ..models.notify import Mention


def delete_post_record(db: Session, post: Post) -> None:
    """删除一篇帖子的完整发布单元；由调用方负责 commit。"""
    pid = post.id
    comment_ids = [r.id for r in db.query(PostComment.id).filter_by(post_id=pid).all()]
    if comment_ids:
        db.query(PostCommentReaction).filter(
            PostCommentReaction.comment_id.in_(comment_ids)
        ).delete(synchronize_session=False)
        db.query(Mention).filter(
            Mention.source_type == "post_comment", Mention.source_id.in_(comment_ids)
        ).delete(synchronize_session=False)
    db.query(PostComment).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(PostReaction).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(PostTag).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(PostFollow).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(PostVariable).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(PostAdminFlag).filter_by(post_id=pid).delete(synchronize_session=False)
    db.query(ContentScope).filter_by(content_type="post", content_id=pid).delete(
        synchronize_session=False
    )
    for attachment in db.query(PostAttachment).filter_by(post_id=pid).all():
        try:
            storage.delete(attachment.file_path)
        except Exception:
            pass
        db.delete(attachment)
    db.delete(post)
