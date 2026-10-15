/* Only interprets keyboard events while the user explicitly records one shortcut. */
(function(root) {
  const modifiers = {ControlLeft:'LeftCtrl',ControlRight:'RightCtrl',AltLeft:'LeftAlt',AltRight:'RightAlt',ShiftLeft:'LeftShift',ShiftRight:'RightShift'};
  function keyName(event) {
    const code = event.code || '';
    if (/^Key[A-Z]$/.test(code)) return code.slice(3);
    if (/^Digit[0-9]$/.test(code)) return code.slice(5);
    if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code;
    return {Space:'Space',Enter:'Enter',Tab:'Tab',Escape:'Esc',ArrowUp:'Up',ArrowDown:'Down',ArrowLeft:'Left',ArrowRight:'Right'}[code] || null;
  }
  function chord(event, held) {
    if (event.metaKey) return null;
    if ([...held].filter(code=>!modifiers[code]).length > 1) return null;
    const key = keyName(event);
    if (!key) return null;
    const result = [];
    for (const [prefix, flag, generic] of [['Control',event.ctrlKey,'Ctrl'],['Alt',event.altKey,'Alt'],['Shift',event.shiftKey,'Shift']]) {
      const names = [...held].filter(code=>code.startsWith(prefix)).map(code=>modifiers[code]).filter(Boolean);
      if (names.length>1) return null;
      if (names.length) result.push(names[0]); else if (flag) result.push(generic);
    }
    if (!result.length && !/^F\d+$/.test(key)) return null;
    return [...result,key].join('+');
  }
  const api = {modifiers,keyName,chord};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ShortcutInput = api;
})(typeof window !== 'undefined' ? window : globalThis);
