package com.openipc.xr.menu;

import java.util.List;

/** The text of a stats page by its id (a {@link MenuItem.Kind#PAGE} item); empty if the id is not this source's. */
public interface PageSource {
    List<String> lines(String pageId);
}
