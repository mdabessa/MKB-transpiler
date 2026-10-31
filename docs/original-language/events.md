# Events

A script is not always started by pressing a key. The mod also runs code when
game state changes; each of those entry points is an **event**.

Marks: ✅ verified, 🧪 observed, ❓ unverified — see the [legend](README.md#confidence-legend).

## Scope of this page

Only events that a script in this repository actually attaches to are
documented. Event names without an example are listed at the end for later, not
described — an event spec that nobody has exercised is worse than no spec.

## How an event is bound

The macro window has one code slot per event. A script installed in a slot runs
when the event fires, with that event's variables already populated — that is
how `%CHAT%` exists inside an `onChat` handler.

In this repository the convention is one file per event, e.g.
[`macros/onChat.mkb`](../../macros/onChat.mkb) ✅.

## Events with a working example

| Event | Fires when | Variables available | Example |
| --- | --- | --- | --- |
| `onLoad` | the macro set is loaded / the client starts | — | [`macros/onLoad.mkb`](../../macros/onLoad.mkb) ✅ |
| `onChat` | a chat line arrives | `%CHAT%`, `%CHATCLEAN%` | [`examples/onChat_kills.txt`](../../examples/onChat_kills.txt) ✅ |
| `onArmourDurabilityChange` | an armour piece loses durability | `%HELMDURABILITY%`, `%CHESTPLATEDURABILITY%`, `%LEGGINGSDURABILITY%`, `%BOOTSDURABILITY%` | [`examples/forum/macro-evite-capacete-quebrar.txt`](../../examples/forum/macro-evite-capacete-quebrar.txt) ✅ |

## `onChat` in practice

`%CHAT%` carries formatting codes, `%CHATCLEAN%` does not, so matching is done
against `%CHATCLEAN%`:

```txt
ifmatches("%CHATCLEAN%","^\[L][^:]+ %PLAYER%(?: \[\w+\])*: (resetar|ocultar|mostrar) kills$",&qual_acao,1);
    ifcontains("%&qual_acao%","resetar");
        set(@&lista_de_kills,"Kill Count");
    endif;
endif;
```

✅ [`examples/onChat_kills.txt`](../../examples/onChat_kills.txt).

Note the escaped brackets (`\[`) — the pattern is a regular expression, not a
literal string (see `IFMATCHES` in [reference/functions.md](reference/functions.md#control-flow)).

## Chat filters

`functions.json` documents three keywords that operate on *this chat message*,
which only makes sense inside `onChat`:

| Keyword | Description (from `functions.json`) |
| --- | --- |
| `MODIFY(<newmessage>)` | Set new content for this chat message |
| `FILTER` | Indicate that this chat message should be filtered and terminate |
| `PASS` | Indicate that this chat message should PASS the filter and terminate |

No script in the corpus uses them, so this page says no more than the inventory
does.

## Not yet documented

The [guide][guide] names these slots as well; no script here attaches to them,
so their trigger conditions and variables are unknown:

`onJoinGame`, `onSendChatMessage`, `onHealthChange`, `onFoodChange`,
`onArmourChange`, `onWorldChange`, `onModeChange`, `onInventorySlotChange`,
`onXPChange`, `onLevelChange`, `onWeatherChange`, `onPickupItem`,
`onPlayerJoined`, `onShowGui`, `onAutoCraftingComplete`, `onConfigChange`.

They stay out of the reference until a script in this repository exercises them.

[guide]: https://forum.craftlandia.com.br/xf/threads/atualizado-guia-de-macro-para-iniciantes.878215/
