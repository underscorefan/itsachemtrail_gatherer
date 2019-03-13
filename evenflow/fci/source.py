import abc
from aiohttp import ClientSession
from typing import List, Tuple, Optional, Dict, Union
from evenflow.helpers.func import mmap
from evenflow.helpers.html import PageOps
from .state import State


URL = 'url'
PAGE = 'page'


class Selectors:
    def __init__(self, nextp: str, entries: str, links: str):
        self.next = nextp
        self.entries = entries
        self.links = links


class FeedReader(abc.ABC):

    @abc.abstractmethod
    def get_name(self) -> str:
        pass

    @abc.abstractmethod
    def to_state(self, over: bool = False):
        pass

    @abc.abstractmethod
    async def fetch_links(self, session: ClientSession) -> 'FeedResult':
        pass

    @abc.abstractmethod
    def recover_state(self, state: State) -> bool:
        pass


class FeedReaderHTML(FeedReader):
    def __init__(self, name: str, url: str, sel: Union[Dict, Selectors], stop_after: int, fake_news: bool):
        self.name = name
        self.url = url
        self.stop_after = stop_after
        self.sel = Selectors(**sel) if isinstance(sel, dict) else sel
        self.fake_news = fake_news

    def get_name(self) -> str:
        return self.name

    def recover_state(self, state: State) -> bool:
        if state.is_over:
            return False
        self.url = state.data[URL]
        self.stop_after = state.data[PAGE]
        return True

    async def fetch_list(self, session: ClientSession) -> Tuple[List[str], str]:
        wr = PageOps(self.url, max_workers=2)
        k_art = "articles"
        k_n = "next"
        res = await wr.fetch_multiple_urls(self.sel.entries, k_art)\
            .fetch_single_url(self.sel.next, k_n)\
            .do_ops(session)
        return res[k_art], res[k_n]

    async def fetch_links(self, session: ClientSession) -> 'FeedResult':
        feed_links, next_page = await self.fetch_list(session)
        next_reader = mmap(next_page, self.__new_page)

        return FeedResult(
            links=await self.__get_links_from(session, *feed_links),
            next_reader=next_reader,
            current_reader_state=self.to_state(over=next_reader is None)
        )

    def to_state(self, over: bool = False) -> State:
        return State(
            name=self.name,
            is_over=over,
            data={
                URL: self.url,
                PAGE: self.stop_after
            })

    def __new_page(self, new_page_url: str) -> Optional['FeedReaderHTML']:
        if self.stop_after == 0:
            return None

        return FeedReaderHTML(
            name=self.name,
            url=new_page_url,
            sel=self.sel,
            stop_after=self.stop_after - 1,
            fake_news=self.fake_news
        )

    async def __get_links_from(self, session: ClientSession, *urls: str) -> Dict[str, Tuple[str, bool]]:
        k_out = "links"
        all_links: Dict[str, Tuple[str, bool]] = {}
        for url in urls:
            article_links = await PageOps(url, max_workers=1)\
                .fetch_multiple_urls(self.sel.links, k_out)\
                .do_ops(session)
            all_links = {
                **all_links,
                **dict(zip(article_links[k_out], [(url, self.fake_news)] * len(article_links[k_out])))
            }
        return all_links


class FeedResult:
    def __init__(
            self,
            links: Dict[str, Tuple[str, bool]],
            next_reader: Optional[FeedReader],
            current_reader_state: State
    ):
        self.links = links
        self.next_reader = next_reader
        self.current_reader_state = current_reader_state
