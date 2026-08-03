import { defineStore } from 'pinia'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    filterLabData: true,
  }),
  actions: {
    setFilterLabData(filter: boolean) {
      this.filterLabData = filter
      localStorage.setItem('filterLabData', String(filter))
    },
    initFilterLabData() {
      const saved = localStorage.getItem('filterLabData')
      if (saved !== null) {
        this.filterLabData = saved === 'true'
      }
    },
  },
})
