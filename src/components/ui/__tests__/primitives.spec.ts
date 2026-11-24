import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Progress,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('UI primitives suite', () => {
  it('re-exports existing and newly added primitives from @/components/ui', () => {
    expect(Button).toBeDefined()
    expect(Progress).toBeDefined()
    expect(Card).toBeDefined()
    expect(Input).toBeDefined()
    expect(Textarea).toBeDefined()
    expect(Label).toBeDefined()
    expect(Select).toBeDefined()
    expect(Switch).toBeDefined()
    expect(Checkbox).toBeDefined()
    expect(Tabs).toBeDefined()
    expect(Collapsible).toBeDefined()
    expect(Dialog).toBeDefined()
    expect(Drawer).toBeDefined()
    expect(Popover).toBeDefined()
    expect(DropdownMenu).toBeDefined()
    expect(Tooltip).toBeDefined()
  })

  it('renders Card variants, slots and consumer styling hooks independently of their appearance', () => {
    const wrapper = mount({
      components: { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter },
      template: `
        <div>
          <Card data-testid="default-card">
            <CardHeader>
              <CardTitle>审批概览</CardTitle>
              <CardDescription>仅展示当前厂区数据</CardDescription>
            </CardHeader>
            <CardContent>正文</CardContent>
            <CardFooter>操作</CardFooter>
          </Card>
          <Card variant="interactive" data-testid="interactive-card" class="consumer-card-hook">可点击卡片</Card>
          <Card variant="subtle" data-testid="subtle-card">内嵌浅卡</Card>
        </div>
      `,
    })

    const defaultCard = wrapper.get('[data-testid="default-card"]')
    expect(defaultCard.attributes('data-variant')).toBe('default')
    expect(defaultCard.get('[data-slot="card-title"]').text()).toBe('审批概览')
    expect(defaultCard.get('[data-slot="card-description"]').text()).toBe('仅展示当前厂区数据')
    expect(defaultCard.get('[data-slot="card-content"]').text()).toBe('正文')
    expect(defaultCard.get('[data-slot="card-footer"]').text()).toBe('操作')
    const interactiveCard = wrapper.get('[data-testid="interactive-card"]')
    expect(interactiveCard.attributes('data-variant')).toBe('interactive')
    expect(interactiveCard.classes()).toContain('consumer-card-hook')
    expect(interactiveCard.text()).toBe('可点击卡片')
    expect(wrapper.get('[data-testid="subtle-card"]').attributes('data-variant')).toBe('subtle')
    wrapper.unmount()
  })

  it('supports v-model and required label states for Input, Textarea and Label', async () => {
    const Host = defineComponent({
      components: { Input, Textarea, Label },
      setup() {
        const code = ref('PO-001')
        const memo = ref('首批备注')
        return { code, memo }
      },
      template: `
        <div>
          <Label for="order-code" required>客户单号</Label>
          <Input id="order-code" v-model="code" size="sm" aria-invalid="true" />
          <Textarea v-model="memo" />
        </div>
      `,
    })

    const wrapper = mount(Host)
    expect(wrapper.get('[data-slot="label"]').text()).toContain('*')

    const input = wrapper.get('[data-slot="input"]')
    expect(input.attributes('data-size')).toBe('sm')
    await input.setValue('PO-002')
    expect(wrapper.vm.code).toBe('PO-002')

    const textarea = wrapper.get('[data-slot="textarea"]')
    await textarea.setValue('更新备注')
    expect(wrapper.vm.memo).toBe('更新备注')
  })

  it('toggles Switch and Checkbox including indeterminate state', async () => {
    const Host = defineComponent({
      components: { Switch, Checkbox },
      setup() {
        const enabled = ref(false)
        const checked = ref<boolean | 'indeterminate'>('indeterminate')
        return { enabled, checked }
      },
      template: `
        <div>
          <Switch v-model="enabled" aria-label="启用自动同步" />
          <Checkbox v-model="checked" aria-label="全选" />
        </div>
      `,
    })

    const wrapper = mount(Host)
    const sw = wrapper.get('[data-slot="switch"]')
    expect(sw.attributes('data-state')).toBe('unchecked')
    await sw.trigger('click')
    expect(wrapper.vm.enabled).toBe(true)

    const cb = wrapper.get('[data-slot="checkbox"]')
    expect(cb.attributes('data-state')).toBe('indeterminate')
    await cb.trigger('click')
    expect(wrapper.vm.checked).toBe(true)
  })

  it('renders an accessible tablist, selection indicator and switches the active panel', async () => {
    const wrapper = mount({
      components: { Tabs, TabsList, TabsTrigger, TabsContent },
      template: `
        <Tabs default-value="overview">
          <TabsList>
            <TabsTrigger value="overview">概览</TabsTrigger>
            <TabsTrigger value="history">记录</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">概览内容</TabsContent>
          <TabsContent value="history">记录内容</TabsContent>
        </Tabs>
      `,
    })

    await nextTick()
    await nextTick()
    expect(wrapper.get('[data-slot="tabs-list"]').attributes('role')).toBe('tablist')
    expect(wrapper.get('[data-slot="tabs-indicator"]').attributes('aria-hidden')).toBe('true')
    expect(wrapper.text()).toContain('概览内容')

    const triggers = wrapper.findAll('[data-slot="tabs-trigger"]')
    expect(triggers[0]!.attributes('aria-selected')).toBe('true')
    expect(triggers[1]!.attributes('aria-selected')).toBe('false')
    await triggers[1]!.trigger('mousedown')
    await triggers[1]!.trigger('click')
    await nextTick()
    expect(triggers[1]!.attributes('aria-selected')).toBe('true')
    expect(triggers[0]!.attributes('aria-selected')).toBe('false')
    expect(wrapper.text()).toContain('记录内容')
    const panel = wrapper.get('[role="tabpanel"][data-state="active"]')
    expect(panel.attributes('id')).toBe(triggers[1]!.attributes('aria-controls'))
    wrapper.unmount()
  })

  it('toggles Collapsible content on trigger click', async () => {
    const wrapper = mount({
      components: { Collapsible, CollapsibleTrigger, CollapsibleContent },
      template: `
        <Collapsible>
          <CollapsibleTrigger>展开详情</CollapsibleTrigger>
          <CollapsibleContent>隐藏的追溯信息</CollapsibleContent>
        </Collapsible>
      `,
    })

    expect(wrapper.get('[data-slot="collapsible"]').attributes('data-state')).toBe('closed')
    await wrapper.get('[data-slot="collapsible-trigger"]').trigger('click')
    expect(wrapper.get('[data-slot="collapsible"]').attributes('data-state')).toBe('open')
    expect(wrapper.text()).toContain('隐藏的追溯信息')
  })

  it('renders an expanded Select with accessible options and selected factory', async () => {
    const wrapper = mount(
      {
        components: { Select, SelectTrigger, SelectValue, SelectContent, SelectItem },
        template: `
          <Select :open="true" model-value="huakang-a">
            <SelectTrigger aria-label="厂区">
              <SelectValue placeholder="请选择厂区" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="huakang-a">华康 A</SelectItem>
              <SelectItem value="huadeng">华登</SelectItem>
            </SelectContent>
          </Select>
        `,
      },
      { attachTo: document.body },
    )

    await nextTick()
    const content = document.body.querySelector('[data-slot="select-content"]')
    expect(content).not.toBeNull()
    const trigger = wrapper.get('[data-slot="select-trigger"]')
    expect(trigger.attributes('role')).toBe('combobox')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(content?.getAttribute('role')).toBe('listbox')
    const options = Array.from(content!.querySelectorAll('[role="option"]'))
    expect(options.map((option) => option.textContent?.trim())).toEqual(['华康 A', '华登'])
    expect(options[0]?.getAttribute('aria-selected')).toBe('true')
    expect(options[1]?.getAttribute('aria-selected')).toBe('false')
    wrapper.unmount()
  })

  it('renders Dialog with an accessible title, description and working close button', async () => {
    const open = ref(true)
    const wrapper = mount(
      {
        components: { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter },
        setup: () => ({ open }),
        template: `
          <Dialog v-model:open="open">
            <DialogContent>
              <DialogHeader>
                <DialogTitle>确认撤回单据</DialogTitle>
                <DialogDescription>撤回后将保留审计记录。</DialogDescription>
              </DialogHeader>
              <DialogFooter>底部动作</DialogFooter>
            </DialogContent>
          </Dialog>
        `,
      },
      { attachTo: document.body },
    )

    await nextTick()
    const dialog = document.body.querySelector('[data-slot="dialog-content"]')
    expect(dialog).not.toBeNull()
    expect(dialog?.getAttribute('role')).toBe('dialog')
    const titleId = dialog?.getAttribute('aria-labelledby')
    const descriptionId = dialog?.getAttribute('aria-describedby')
    expect(titleId).toBeTruthy()
    expect(descriptionId).toBeTruthy()
    expect(document.getElementById(titleId!)?.textContent).toContain('确认撤回单据')
    expect(document.getElementById(descriptionId!)?.textContent).toContain('撤回后将保留审计记录。')

    const closeBtn = document.body.querySelector('[data-slot="dialog-close-button"]') as HTMLButtonElement | null
    expect(closeBtn?.getAttribute('aria-label')).toBe('关闭')
    closeBtn?.click()
    await nextTick()
    expect(open.value).toBe(false)
    wrapper.unmount()
  })

  it('renders the requested Drawer side and closes through an accessible control', async () => {
    const open = ref(true)
    const wrapper = mount(
      {
        components: { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerFooter },
        setup: () => ({ open }),
        template: `
          <Drawer v-model:open="open">
            <DrawerContent side="bottom">
              <DrawerHeader>
                <DrawerTitle>批次详情</DrawerTitle>
                <DrawerDescription>侧滑抽屉内容</DrawerDescription>
              </DrawerHeader>
              <DrawerFooter>完成</DrawerFooter>
            </DrawerContent>
          </Drawer>
        `,
      },
      { attachTo: document.body },
    )

    await nextTick()
    const drawer = document.body.querySelector('[data-slot="drawer-content"]')
    expect(drawer).not.toBeNull()
    expect(drawer?.getAttribute('data-side')).toBe('bottom')
    expect(drawer?.getAttribute('role')).toBe('dialog')
    const titleId = drawer?.getAttribute('aria-labelledby')
    expect(titleId).toBeTruthy()
    expect(document.getElementById(titleId!)?.textContent).toContain('批次详情')
    const close = drawer!.querySelector<HTMLButtonElement>('[data-slot="drawer-close-button"]')
    expect(close?.getAttribute('aria-label')).toBe('关闭')
    close!.click()
    await nextTick()
    expect(open.value).toBe(false)
    wrapper.unmount()
  })

  it('renders Popover, DropdownMenu and Tooltip content and preserves destructive action semantics', async () => {
    const wrapper = mount(
      {
        components: {
          Popover,
          PopoverTrigger,
          PopoverContent,
          DropdownMenu,
          DropdownMenuTrigger,
          DropdownMenuContent,
          DropdownMenuLabel,
          DropdownMenuItem,
          DropdownMenuSeparator,
          TooltipProvider,
          Tooltip,
          TooltipTrigger,
          TooltipContent,
        },
        template: `
          <div>
            <Popover :open="true">
              <PopoverTrigger>筛选</PopoverTrigger>
              <PopoverContent>筛选面板</PopoverContent>
            </Popover>
            <DropdownMenu :open="true">
              <DropdownMenuTrigger>更多</DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>操作</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive">删除单据</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <TooltipProvider>
              <Tooltip :open="true">
                <TooltipTrigger>图标</TooltipTrigger>
                <TooltipContent>查看完整编号</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        `,
      },
      { attachTo: document.body },
    )

    await nextTick()
    const popover = document.body.querySelector('[data-slot="popover-content"]')
    expect(popover?.textContent).toContain('筛选面板')
    const menu = document.body.querySelector('[data-slot="dropdown-menu-content"]')
    expect(menu?.getAttribute('role')).toBe('menu')
    const action = menu?.querySelector('[data-slot="dropdown-menu-item"]')
    expect(action?.getAttribute('role')).toBe('menuitem')
    expect(action?.getAttribute('data-variant')).toBe('destructive')
    expect(action?.textContent).toContain('删除单据')
    expect(document.body.querySelector('[data-slot="tooltip-content"]')?.textContent).toContain('查看完整编号')
    wrapper.unmount()
  })
})
