import { computed, type Directive, ref, type Ref } from "vue";
import type { PermItem } from "../api";

const vIndeterminate: Directive<HTMLInputElement, boolean> = {
  mounted(el, binding) {
    el.indeterminate = binding.value;
  },
  updated(el, binding) {
    el.indeterminate = binding.value;
  },
};

function getDescendants(childrenMap: Map<number, PermItem[]>, permId: number): number[] {
  const result: number[] = [];
  const queue = [permId];
  while (queue.length) {
    const id = queue.shift()!;
    const children = childrenMap.get(id) || [];
    for (const child of children) {
      result.push(child.perm_id);
      queue.push(child.perm_id);
    }
  }
  return result;
}

export function usePermissionTree(permissions: Ref<PermItem[]>, checked: Ref<Set<number>>) {
  const indeterminate = ref<Set<number>>(new Set());

  const childrenMap = computed(() => {
    const map = new Map<number, PermItem[]>();
    for (const item of permissions.value) {
      const list = map.get(item.parent_id) || [];
      list.push(item);
      map.set(item.parent_id, list);
    }
    return map;
  });

  const parentMap = computed(() => {
    const map = new Map<number, number>();
    for (const item of permissions.value) {
      map.set(item.perm_id, item.parent_id);
    }
    return map;
  });

  function recomputeNode(nextChecked: Set<number>, nextIndeterminate: Set<number>, permId: number) {
    const children = childrenMap.value.get(permId) || [];
    if (!children.length) {
      nextIndeterminate.delete(permId);
      return;
    }
    const allChecked = children.length && children.every((c) => nextChecked.has(c.perm_id));
    const someSelected = children.some(
      (c) => nextChecked.has(c.perm_id) || nextIndeterminate.has(c.perm_id)
    );
    if (allChecked) {
      nextChecked.add(permId);
      nextIndeterminate.delete(permId);
    } else if (someSelected) {
      nextChecked.delete(permId);
      nextIndeterminate.add(permId);
    } else {
      nextChecked.delete(permId);
      nextIndeterminate.delete(permId);
    }
  }

  function recomputeUpwards(nextChecked: Set<number>, nextIndeterminate: Set<number>, permId: number) {
    let current = permId;
    while (true) {
      const parent = parentMap.value.get(current);
      if (parent === undefined || parent === 0) break;
      recomputeNode(nextChecked, nextIndeterminate, parent);
      current = parent;
    }
  }

  function initChecked(ids: number[] | Iterable<number>) {
    const nextChecked = new Set<number>(ids);
    const nextIndeterminate = new Set<number>();
    const leaves = permissions.value.filter((p) => !(childrenMap.value.get(p.perm_id)?.length));
    for (const leaf of leaves) {
      recomputeUpwards(nextChecked, nextIndeterminate, leaf.perm_id);
    }
    // 单独对所有父节点再归一化一次，确保多叶子共享父节点时父节点最终一致
    for (const item of permissions.value) {
      if ((childrenMap.value.get(item.perm_id)?.length || 0) > 0) {
        recomputeNode(nextChecked, nextIndeterminate, item.perm_id);
      }
    }
    checked.value = nextChecked;
    indeterminate.value = nextIndeterminate;
  }

  function toggle(permId: number) {
    const nextChecked = new Set<number>(checked.value);
    const nextIndeterminate = new Set<number>(indeterminate.value);
    const children = childrenMap.value.get(permId) || [];

    if (children.length) {
      const willCheck = !(nextChecked.has(permId) || nextIndeterminate.has(permId));
      if (willCheck) {
        nextChecked.add(permId);
      } else {
        nextChecked.delete(permId);
      }
      nextIndeterminate.delete(permId);
      for (const id of getDescendants(childrenMap.value, permId)) {
        if (willCheck) {
          nextChecked.add(id);
        } else {
          nextChecked.delete(id);
        }
        nextIndeterminate.delete(id);
      }
    } else {
      if (nextChecked.has(permId)) {
        nextChecked.delete(permId);
      } else {
        nextChecked.add(permId);
      }
    }

    recomputeUpwards(nextChecked, nextIndeterminate, permId);
    checked.value = nextChecked;
    indeterminate.value = nextIndeterminate;
  }

  return {
    indeterminate,
    toggle,
    initChecked,
    vIndeterminate,
  };
}
