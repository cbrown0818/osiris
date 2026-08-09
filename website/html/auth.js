(() => {
  "use strict";

  const TOKEN_KEY = "osiris_api_token_session";
  const originalFetch = window.fetch.bind(window);

  function resolveRequestUrl(input) {
    try {
      const rawUrl =
        typeof input === "string"
          ? input
          : input.url;

      return new URL(rawUrl, window.location.href);
    } catch (_error) {
      return null;
    }
  }

  function isOsirisApiRequest(input) {
    const url = resolveRequestUrl(input);

    if (!url) {
      return false;
    }

    const sameOrigin =
      url.origin === window.location.origin;

    const apiPath =
      url.pathname === "/api" ||
      url.pathname.startsWith("/api/");

    return sameOrigin && apiPath;
  }

  function isPublicApiRequest(input) {
    const url = resolveRequestUrl(input);

    if (!url) {
      return false;
    }

    return (
      url.pathname === "/api/health" ||
      url.pathname === "/api/health/"
    );
  }

  function getToken() {
    let token =
      sessionStorage.getItem(TOKEN_KEY) || "";

    if (!token) {
      token =
        window.prompt(
          "Enter your private OSIRIS API token. " +
          "It will remain only in this browser session."
        ) || "";

      token = token.trim();

      if (token) {
        sessionStorage.setItem(
          TOKEN_KEY,
          token
        );
      }
    }

    return token;
  }

  window.osirisForgetApiToken =
    function osirisForgetApiToken() {
      sessionStorage.removeItem(TOKEN_KEY);
    };

  window.fetch =
    async function osirisAuthenticatedFetch(
      input,
      init = {}
    ) {
      if (!isOsirisApiRequest(input)) {
        return originalFetch(input, init);
      }

      const baseHeaders =
        input instanceof Request
          ? input.headers
          : undefined;

      const headers =
        new Headers(baseHeaders || {});

      new Headers(
        init.headers || {}
      ).forEach((value, key) => {
        headers.set(key, value);
      });

      if (!isPublicApiRequest(input)) {
        const token = getToken();

        if (token) {
          headers.set(
            "Authorization",
            `Bearer ${token}`
          );
        }
      }

      const response =
        await originalFetch(input, {
          ...init,
          headers,
          cache: "no-store",
          credentials: "omit",
        });

      if (response.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
      }

      return response;
    };
})();
