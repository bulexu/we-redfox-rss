import translate from "i18n-jsautotranslate";

// 原 translate.zvo.cn 免费接口已不可用（请求被重置），
// 改用浏览器端 Edge 翻译通道，无需服务端接口。
translate.service.use("client.edge");
translate.language.setLocal("chinese_simplified");

export const hash = (str: string): string => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return hash.toString();
};
const key = "c-Hash-Body";
export const set_hash = (): void => {
  localStorage.setItem(key, hash(document.body.innerText));
};

export const get_hash = (): string | null => {
  return localStorage.getItem(key);
};

export const translatePage = () => {
  const savedLanguage = localStorage.getItem("language");
  if (savedLanguage) {
    setTimeout(() => {
      // 刷新后 node 缓存已清空，直接按已保存语种重新翻译。
      // 不再用 body 文本 hash 判断，避免上次「翻译尚未返回就记录 hash」
      // 导致刷新后被误判为未变化而跳过翻译。
      translate.changeLanguage(savedLanguage);
      set_hash();
    }, 1000); // 延时1000毫秒后执行语言切换
  }
};

export const setCurrentLanguage = (language: string) => {
  translate.changeLanguage(language);
  localStorage.setItem("language", language);
};
