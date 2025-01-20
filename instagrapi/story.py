from urllib.parse import urlparse
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from .types import StoryBuild, StoryMention, StorySticker

try:
    from moviepy.editor import CompositeVideoClip, ImageClip, TextClip, VideoFileClip
except ImportError:
    raise Exception("Please install moviepy==1.0.3 and retry")

try:
    from PIL import Image
except ImportError:
    raise Exception("You don't have PIL installed. Please install PIL or Pillow>=8.1.1")


class StoryBuilder:
    """
    Helpers for Story building
    """

    width = 720
    height = 1280

    def __init__(self, path: Path, caption: str = "", mentions: Optional[List[StoryMention]] = None, bgpath: Optional[Path] = None):
        """
        Initialization function

        Parameters
        ----------
        path : Path
            Path for a file
        caption : str, optional
            Media caption, default value is ""
        mentions : List[StoryMention], optional
            List of mentions to be tagged on this upload, default value is empty list
        bgpath : Path, optional
            Path for a background image, default value is None

        Returns
        -------
        Void
        """
        if mentions is None:
            mentions = []
        self.path = Path(path)
        self.caption = caption
        self.mentions = mentions
        self.bgpath = Path(bgpath) if bgpath else None

    def build_main(
        self,
        clip,
        max_duration: int = 0,
        font: str = "Arial",
        fontsize: int = 100,
        color: str = "white",
        link: str = "",
        link_clip_left: Optional[float] = None,
        link_clip_top: Optional[float] = None,
        link_clip_width: int = 400,
        link_fontsize: int = 32,
        link_color: str = "blue",
        link_bg_color: str = "white",
        link_fadein: float = 3.0,
        link_sticker_z: float = 0.0,
        link_sticker_rotation: float = 0.0,
    ) -> StoryBuild:
        """
        Build clip

        Parameters
        ----------
        clip : (VideoFileClip, ImageClip)
            An object of either VideoFileClip or ImageClip
        max_duration : int, optional
            Duration of the clip if a video clip, default value is 0
        font : str, optional
            Name of font for text clip
        fontsize : int, optional
            Size of font
        color : str, optional
            Color of text
        link : str, optional
            A URL or link string

        link_clip_left : float, optional
            X座標(ピクセル)でのリンクテキスト左位置(未指定なら中央計算)
        link_clip_top : float, optional
            Y座標(ピクセル)でのリンクテキスト上位置(未指定なら自動計算)
        link_clip_width : int, optional
            リンクテキストの横幅
        link_fontsize : int, optional
            リンクテキストのフォントサイズ
        link_color : str, optional
            リンクテキストの文字色
        link_bg_color : str, optional
            リンクテキストの背景色
        link_fadein : float, optional
            リンクテキストのフェードイン秒数
        link_sticker_z : float, optional
            リンクステッカーのZ順序
        link_sticker_rotation : float, optional
            リンクステッカーの回転角度

        Returns
        -------
        StoryBuild
            An object of StoryBuild
        """
        clips = []
        stickers = []

        # 1) 背景クリップ追加
        if self.bgpath:
            assert self.bgpath.exists(), f"Wrong path to background {self.bgpath}"
            background = ImageClip(str(self.bgpath))
            clips.append(background)

        # 2) メイン (動画/画像) クリップの配置
        clip_left = (self.width - clip.size[0]) / 2
        clip_top = (self.height - clip.size[1]) / 2
        # もし上下の余白が多いなら若干上に持ち上げる
        if clip_top > 90:
            clip_top -= 50

        media_clip = clip.set_position((clip_left, clip_top))
        clips.append(media_clip)

        # 3) キャプション (mentions があればユーザ名をキャプションに使う)
        mention = self.mentions[0] if self.mentions else None
        caption_text = self._get_caption_text(mention)  # 下で定義する小メソッド

        # 4) キャプション用テキストクリップ (共通処理で生成)
        text_clip = None
        if caption_text:
            text_clip = self._create_text_clip(
                text=caption_text,
                color=color,
                font=font,
                fontsize=fontsize,
                max_width=600,   # キャプション幅
                pos_top=clip_top + clip.size[1] + 50,
            )
            if text_clip:
                clips.append(text_clip)

        # 5) リンクテキストクリップ
        if link:
            # リンク文字列から表示用ドメインなどを抽出
            url = urlparse(link)
            link_text = url.netloc if url.netloc else link

            # 座標や幅が指定されていなければデフォルト計算
            if link_clip_left is None:
                link_clip_left = (self.width - link_clip_width) / 2
            if link_clip_top is None:
                link_clip_top = clip.size[1] / 2

            link_clip_obj = self._create_text_clip(
                text=link_text,
                color=link_color,
                font=font,
                fontsize=link_fontsize,
                max_width=link_clip_width,
                bg_color=link_bg_color,
                fadein_sec=link_fadein,
                pos_left=link_clip_left,
                pos_top=link_clip_top,
            )

            if link_clip_obj:
                clips.append(link_clip_obj)
                # ステッカー(Sticker)を生成
                link_sticker = StorySticker(
                    x=round(link_clip_left / self.width, 7),
                    y=round(link_clip_top / self.height, 7),
                    z=link_sticker_z,
                    width=round(link_clip_obj.size[0] / self.width, 7),
                    height=round(link_clip_obj.size[1] / self.height, 7),
                    rotation=link_sticker_rotation,
                    type="story_link",
                    extra=dict(
                        link_type="web",
                        url=str(link),
                        tap_state_str_id="link_sticker_default",
                    ),
                )
                stickers.append(link_sticker)

        # 6) メンション領域の調整
        mentions = []
        if mention and text_clip:
            self._adjust_mention_geometry(mention, text_clip)  # 下で定義する小メソッド
            mentions = [mention]

        # 7) 動画長の算出
        duration = self._calculate_duration(clip, max_duration)

        # 8) クリップを合成
        destination = tempfile.mktemp(".mp4")
        cvc = CompositeVideoClip(clips, size=(self.width, self.height)).set_fps(24).set_duration(duration)
        cvc.write_videofile(destination, codec="libx264", audio=True, audio_codec="aac")

        # 9) 15秒以上の場合、分割書き出し
        paths = []
        if duration > 15:
            for i in range(duration // 15 + (1 if duration % 15 else 0)):
                path = tempfile.mktemp(".mp4")
                start = i * 15
                rest = duration - start
                end = start + (rest if rest < 15 else 15)
                sub = cvc.subclip(start, end)
                sub.write_videofile(path, codec="libx264", audio=True, audio_codec="aac")
                paths.append(path)

        return StoryBuild(mentions=mentions, path=destination, paths=paths, stickers=stickers)


    def video(self, max_duration: int = 0, font: str = "Arial", fontsize: int = 100, color: str = "white", link: str = "") -> StoryBuild:
        """
        Build CompositeVideoClip from source video

        Parameters
        ----------
        max_duration: int, optional
            Duration of the clip if a video clip, default value is 0
        font: str, optional
            Name of font for text clip
        fontsize: int, optional
            Size of font
        color: str, optional
            Color of text
        link: str, optional
            A URL or link string

        Returns
        -------
        StoryBuild
            An object of StoryBuild
        """
        clip = VideoFileClip(str(self.path), has_mask=True)
        build = self.build_main(clip, max_duration, font, fontsize, color, link)
        clip.close()
        return build

    def photo(self, max_duration: int = 0, font: str = "Arial", fontsize: int = 100, color: str = "white", link: str = "") -> StoryBuild:
        """
        Build CompositeVideoClip from source image

        Parameters
        ----------
        max_duration: int, optional
            Duration of the clip if a video (or simply display time for an image)
            default value is 0
        font: str, optional
            Name of font for text clip
        fontsize: int, optional
            Size of font
        color: str, optional
            Color of text
        link: str, optional
            A URL or link string

        Returns
        -------
        StoryBuild
            An object of StoryBuild
        """

        with Image.open(self.path) as im:
            image_width, image_height = im.size

        width_reduction_percent = self.width / float(image_width)
        height_in_ratio = int(float(image_height) * width_reduction_percent)

        clip = ImageClip(str(self.path)).resize(width=self.width, height=height_in_ratio)
        return self.build_main(clip, max_duration or 15, font, fontsize, color, link)
