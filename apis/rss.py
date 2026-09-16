from fastapi import APIRouter, Depends, Query, HTTPException, Request,Response
from fastapi import status
from fastapi.responses import Response
from core.db import DB
from core.rss import RSS
from core.models.feed import Feed
import json
from .base import success_response, error_response
from core.auth import get_current_user
from core.config import cfg
from apis.base import format_search_kw
from core.print import print_error,print_success


def clamp_rss_limit(limit: int) -> int:
    """Clamp RSS item count to configured bounds to avoid oversized feeds."""
    default_page_size = int(cfg.get("rss.page_size", 30) or 30)
    max_items = int(cfg.get("rss.max_items", default_page_size) or default_page_size)
    if max_items < 1:
        max_items = default_page_size if default_page_size > 0 else 30
    return min(limit, max_items)
def verify_rss_access(current_user: dict = Depends(get_current_user)):
    """
    RSS访问认证方法
    :param current_user: 当前用户信息
    :return: 认证通过返回用户信息，否则抛出HTTP异常
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response(
                code=40101,
                message="未授权的RSS访问"
            )
        )
    return current_user

router = APIRouter(prefix="/rss",tags=["Rss"])
feed_router = APIRouter(prefix="/feed",tags=["Feed"])

@router.get("/{feed_id}/api", summary="获取特定RSS源详情")
async def get_rss_source(
    feed_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    # current_user: dict = Depends(verify_rss_access)
):
    return await get_mp_articles_source(request=request,feed_id=feed_id, limit=limit,offset=offset, is_update=True)





@router.get("/fresh", summary="更新并获取RSS订阅列表")
async def update_rss_feeds( 
    request: Request,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    # current_user: dict = Depends(get_current_user)
):
    return await get_rss_feeds(request=request, limit=limit,offset=offset, is_update=True)

@router.get("", summary="获取RSS订阅列表")
async def get_rss_feeds(
    request: Request,
    limit: int = Query(10, ge=1, le=30),
    offset: int = Query(0, ge=0),
    is_update:bool=False,
    # current_user: dict = Depends(get_current_user)
):
    limit = clamp_rss_limit(limit)
    rss=RSS(name=f'all_{limit}_{offset}')
    rss_xml=rss.get_cache()
    if rss_xml is not None  and is_update==False:
         return Response(
            content=rss_xml,
            media_type="application/xml"
        )
    session = DB.get_session()
    try:
        total = session.query(Feed).count()
        feeds = session.query(Feed).order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        rss_domain=cfg.get("rss.base_url",request.base_url)
        # 转换为RSS格式数据
        from datetime import datetime, timezone, timedelta
        # assume CST (UTC+8) for naive timestamps
        cst = timezone(timedelta(hours=8))
        rss_list = [{
            "id": str(feed.id),
            "title": feed.name,
            "link":  f"{rss_domain}rss/{feed.id}",
            "description": feed.intro,
            "image": feed.cover,
            "updated": (feed.created_at if getattr(feed.created_at, 'tzinfo', None) is not None else feed.created_at.replace(tzinfo=cst)).isoformat()
        } for feed in feeds]
        
        # 生成RSS XML
        rss_xml = rss.generate_rss(rss_list, title="WeRSS订阅",link=rss_domain)
        
        return Response(
            content=rss_xml,
            media_type="application/xml"
        )
    except Exception as e:
        print(f"获取RSS订阅列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message="获取RSS订阅列表失败"
            )
        )

@router.get("/content/{content_id}", summary="获取缓存的文章内容")
async def get_rss_feed(content_id: str):
    rss = RSS()
    content = rss.get_cached_content(content_id)
      
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(
                code=40402,
                message="文章内容未找到"
            )
        )
    title=content['title']
    html='''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="X-UA-Compatible" content="ie=edge">
        <title>{title}</title>
        </head>
    <body>
    <center>
    <h1 style="text-align:center;">{title}</h1>
    <div class="author">来源:{source}</div>
    <div class="author">发布时间:{publish_time}</div>
    <div class="copyright">
        <p>
        本文章仅用于学习和交流目的，不代表本网站观点和立场，如涉及版权问题，请及时联系我们删除。
        </p>
    </div>
    <div id=content>{text}</div>
    </center>
    </body>
    </html>
    '''
    text=rss.add_logo_prefix_to_urls(content['content'])
    html=html.format(title=title,text=text,source=content['name'],publish_time=content['publish_time'])
    return Response(
            content=html,
            media_type="text/html"
        )
def UpdateArticle(art:dict):
            return DB.add_article(art)


@router.api_route("/{feed_id}/fresh", summary="更新并获取公众号文章RSS")
async def update_rss_feeds( 
    request: Request,
    feed_id: str,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    # current_user: dict = Depends(get_current_user)
):
        #如果需要放开授权，请只允许内网访问，防止 被利用攻击 放开授权办法，注释上面current_user: dict = Depends(get_current_user)

        # from core.models.feed import Feed
        # mp = DB.session.query(Feed).filter(Feed.id == feed_id).first()
        # from core.wx import WxGather
        # wx=WxGather().Model()
        # wx.get_Articles(mp.faker_id,Mps_id=mp.id,CallBack=UpdateArticle)
        # result=wx.articles

        return await get_mp_articles_source(request=request,feed_id=feed_id, limit=limit,offset=offset, is_update=True)



@router.get("/{feed_id}", summary="获取公众号文章")
async def get_mp_articles_source(
    request: Request,
    feed_id: str=None,
    tag_id:str=None,
    ext:str="xml",
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw:str="",
    is_update:bool=True,
    content_type:str=Query(None,alias="ctype"),
    template:str=None
    # current_user: dict = Depends(get_current_user)
):
    limit = clamp_rss_limit(limit)
    rss=RSS(name=f'{tag_id}_{feed_id}_{limit}_{offset}',ext=ext)
    rss.set_content_type(content_type)
    rss_xml = rss.get_cache()
    if rss_xml is not None and is_update==False:
         return Response(
            content=rss_xml,
            media_type=rss.get_type()
        )
    session = DB.get_session()
    try:
        from core.models.article import Article
        from core.models.tags import Tags
        # 查询公众号信息
        feed = session.query(Feed)
        query=session.query(Feed, Article).join(Article, Feed.id == Article.feed_id)
        rss_domain = str(cfg.get("rss.base_url", str(request.base_url))).rstrip("/") + "/"
        if tag_id is not None:
            feed_link = f"{rss_domain}feed/tag/{tag_id}.{ext}"
        elif kw != "":
            target_feed_id = feed_id or "all"
            feed_link = f"{rss_domain}feed/search/{kw}/{target_feed_id}.{ext}"
        else:
            target_feed_id = feed_id or "all"
            feed_link = f"{rss_domain}feed/{target_feed_id}.{ext}"
        if feed_id not in ["all",None]:
            feed=feed.filter(Feed.id == feed_id).first()
            query=query.filter(Article.feed_id==feed_id)
        else:
            feed=Feed()
            feed.name=cfg.get("rss.title","WeRss") or "WeRss"
            feed.intro=cfg.get("rss.description") or "WeRss高效订阅我的公众号"
            feed.cover=cfg.get("rss.cover") or f"{rss_domain}static/logo.svg"
            #如果传入了tag_id就加载tag对应的订阅信息
            if tag_id is not None:
                tags=session.query(Tags).filter(Tags.id == tag_id).first()
                if tags:
                    feed_ids = [str(mp['id']) for mp in json.loads(tags.feed_ids)] if tags.feed_ids else []
                    query=query.filter(Feed.id.in_(feed_ids))
                    feed.name = tags.name
                    feed.intro = tags.intro
                    feed.cover = f'{rss_domain}{tags.cover}'

        
        if not feed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
      
        # 查询文章列表
        total = query.count()
        # articles = query.order_by(Article.publish_time.desc()).limit(limit).offset(offset).all()
        if kw!="":
            query=query.filter(format_search_kw(kw))
        articles =query.order_by(Article.publish_time.desc()).limit(limit).offset(offset).all()
        # 转换为RSS格式数据
        from datetime import datetime, timezone, timedelta
        cst = timezone(timedelta(hours=8))
        rss_list = [{
            "id": str(article.id),
            "title": article.title or "",
            "link":  f"{rss_domain}/views/article/{article.id}" if cfg.get("rss.local",False) else article.url,
            "description": article.description if article.description != "" else article.title or "",
            "content": article.content or "",
            "image": article.pic_url or "",
            "name":_feed.name or "",
            "updated": datetime.fromtimestamp(article.publish_time, tz=cst),
            "feed": {
                    "id":_feed.id,
                    "name":_feed.name,
                    "cover":_feed.cover,
                    "intro":_feed.intro
            }
        } for _feed,article in articles]


        # 缓存文章内容
        for _feed,article in articles:
            content_data = {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "publish_time": article.publish_time,
                "feed_id": article.feed_id,
                "pic_url": article.pic_url,
                "name": _feed.name
            }
            rss.cache_content(article.id, content_data)
        # 生成RSS XML
        rss_xml = rss.generate(rss_list,ext=ext, title=f"{feed.name}",link=feed_link,description=feed.intro,image_url=feed.cover,template=template)
        
        return Response(
            content=rss_xml,
            media_type=rss.get_type()
        )
    except Exception as e:
        print_error(f"获取RSS错误:{e}")
        # raise
        return Response(
             content=rss_xml,
             media_type=rss.get_type()
        )
    


@feed_router.get("/{feed_id}.{ext}", summary="获取公众号文章源")
async def rss(
    request: Request,
    feed_id: str,
    ext: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw:str="",
    content_type:str=Query(None,alias="ctype"),
    is_update:bool=True
):
    return await get_mp_articles_source(request=request,feed_id=feed_id, limit=limit,offset=offset, is_update=is_update,ext=ext,kw=kw,content_type=content_type)


@feed_router.get("/search/{kw}/{feed_id}.{ext}", summary="获取公众号文章源")
async def rss(
    request: Request,
    feed_id: str,
    ext: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw:str="",
    content_type:str=Query(None,alias="ctype"),
    is_update:bool=True
):
    return await get_mp_articles_source(request=request,feed_id=feed_id, limit=limit,offset=offset, is_update=is_update,ext=ext,kw=kw,content_type=content_type)
@feed_router.get("/tag/{tag_id}.{ext}", summary="获取公众号文章源")
async def rss(
    request: Request,
    tag_id:str="",
    feed_id: str=None,
    ext: str="jmd",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw:str="",
    content_type:str=Query(None,alias="ctype"),
    is_update:bool=True
):
    return await get_mp_articles_source(request=request,feed_id=feed_id, tag_id=tag_id,limit=limit,offset=offset, is_update=is_update,ext=ext,kw=kw,content_type=content_type)


# ===== 小红书 (XHS) 专用 RSS =====
# 区别于公众号:
#   * description 用 workDesc 前 200 字 (公众号无 workDesc, 走 title 回退)
#   * content 始终保留 workDesc 全文,  RSS reader 里可读完整笔记正文
#   * 不嵌入视频/多图 (按 Q13 设计: 后续多图再加)
#   * 缓存 key 与公众号隔离, 防止互相覆盖

XHS_DESC_MAX_CHARS = 200


@router.get("/xhs/{feed_id}", summary="获取 XHS feed 的 RSS")
async def get_xhs_feed_rss(
    request: Request,
    feed_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if not (feed_id.startswith("XHS_KW_") or feed_id.startswith("XHS_U_")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                code=40001,
                message="非 XHS feed_id",
            ),
        )

    limit = clamp_rss_limit(limit)
    rss = RSS(name=f"xhs_{feed_id}_{limit}_{offset}")
    rss_xml = rss.get_cache()
    if rss_xml is not None:
        return Response(content=rss_xml, media_type=rss.get_type())

    session = DB.get_session()
    try:
        from core.models.article import Article
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40403, message="XHS 订阅不存在"),
            )

        rss_domain = str(cfg.get("rss.base_url", str(request.base_url))).rstrip("/") + "/"
        feed_link = f"{rss_domain}feed/xhs/{feed_id}.rss"

        rows = (
            session.query(Article)
            .filter(Article.feed_id == feed_id)
            .order_by(Article.publish_time.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        from datetime import datetime, timezone, timedelta
        cst = timezone(timedelta(hours=8))

        def _truncate(text: str, n: int = XHS_DESC_MAX_CHARS) -> str:
            if not text:
                return ""
            text = text.strip()
            return text if len(text) <= n else text[: n - 1] + "…"

        rss_list = [{
            "id": str(a.id),
            "title": a.title or "",
            "link": a.url or f"{rss_domain}views/article/{a.id}",
            "description": _truncate(a.content or a.title or ""),
            "content": a.content or "",
            "image": a.pic_url or "",
            "name": feed.name or "",
            "updated": datetime.fromtimestamp(a.publish_time or 0, tz=cst),
            "feed": {
                "id": feed.id,
                "name": feed.name,
                "cover": feed.cover,
                "intro": feed.intro,
            },
        } for a in rows]

        # 内容缓存 (用于 /rss/content/{id} 详情页)
        for a in rows:
            rss.cache_content(a.id, {
                "id": a.id,
                "title": a.title,
                "content": a.content,
                "publish_time": a.publish_time,
                "feed_id": a.feed_id,
                "pic_url": a.pic_url,
                "name": feed.name,
            })

        rss_xml = rss.generate_rss(
            rss_list,
            title=f"XHS: {feed.name}",
            link=feed_link,
            description=feed.intro or "",
            image_url=feed.cover or "",
        )
        return Response(content=rss_xml, media_type=rss.get_type())
    except HTTPException:
        raise
    except Exception as e:
        print_error(f"获取 XHS RSS 错误:{e}")
        if rss_xml is not None:
            return Response(content=rss_xml, media_type=rss.get_type())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50002, message="获取 XHS RSS 失败"),
        )
    finally:
        try:
            session.close()
        except Exception:
            pass


@feed_router.get("/xhs/{feed_id}.{ext}", summary="XHS RSS (feed_router 别名)")
async def xhs_rss(
    request: Request,
    feed_id: str,
    ext: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await get_xhs_feed_rss(
        request=request,
        feed_id=feed_id,
        limit=limit,
        offset=offset,
    )


