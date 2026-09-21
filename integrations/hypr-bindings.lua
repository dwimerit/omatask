-- Omarchy 4.x / Lua. Check `omarchy menu keybindings --print` for conflicts first.
-- Add to ~/.config/hypr/bindings.lua; choose unused keys or explicitly hl.unbind.
o.bind("SUPER + ALT + T", "Today's tasks", "omarchy-shell shell toggle local.omatask")
o.bind("SUPER + ALT + N", "Quick task", "omatask-panel quick")
