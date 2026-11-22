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

  it('renders Card variants with L1 surface material and interactive elevation', () => {
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
          <Card variant="interactive" data-testid="interactive-card">可点击卡片</Card>
          <Card variant="subtle" data-testid="subtle-card">内嵌浅卡</Card>
        </div>
      `,
    })

    expect(wrapper.get('[data-testid="default-card"]').classes()).toContain('surface-l1')
    expect(wrapper.get('[data-testid="interactive-card"]').classes()).toContain('hover:shadow-elevation-2')
    expect(wrapper.get('[data-testid="subtle-card"]').attributes('data-variant')).toBe('subtle')
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

  it('renders Tabs with L2 glass chrome list, spring indicator and tab switching', async () => {
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
    expect(wrapper.get('[data-slot="tabs-list"]').classes()).toContain('glass-chrome')
    expect(wrapper.find('[data-slot="tabs-indicator"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('概览内容')

    const triggers = wrapper.findAll('[data-slot="tabs-trigger"]')
    await triggers[1]!.trigger('mousedown')
    await triggers[1]!.trigger('click')
    await nextTick()
    expect(triggers[1]!.attributes('data-state')).toBe('active')
    expect(wrapper.text()).toContain('记录内容')
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

  it('renders Select trigger and L3 glass dropdown content when open', async () => {
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
    expect(content?.classList.contains('glass-float')).toBe(true)
    expect(document.body.textContent).toContain('华康 A')
    wrapper.unmount()
  })

  it('renders Dialog with L3 glass surface, aria title and close button', async () => {
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
    expect(dialog?.classList.contains('glass-float')).toBe(true)

    const closeBtn = document.body.querySelector('[data-slot="dialog-close-button"]') as HTMLButtonElement | null
    expect(closeBtn?.getAttribute('aria-label')).toBe('关闭')
    closeBtn?.click()
    await nextTick()
    expect(open.value).toBe(false)
    wrapper.unmount()
  })

  it('renders Drawer with L3 glass surface and directional slide classes', async () => {
    const wrapper = mount(
      {
        components: { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription, DrawerFooter },
        template: `
          <Drawer :open="true">
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
    expect(drawer?.classList.contains('glass-float')).toBe(true)
    expect(drawer?.classList.contains('ui-drawer-bottom')).toBe(true)
    wrapper.unmount()
  })

  it('renders Popover, DropdownMenu (with destructive item) and Tooltip with L3 glass surfaces', async () => {
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
    expect(document.body.querySelector('[data-slot="popover-content"]')?.classList.contains('glass-float')).toBe(true)
    expect(document.body.querySelector('[data-slot="dropdown-menu-content"]')?.classList.contains('glass-float')).toBe(true)
    expect(document.body.querySelector('[data-slot="dropdown-menu-item"]')?.getAttribute('data-variant')).toBe('destructive')
    expect(document.body.querySelector('[data-slot="tooltip-content"]')?.classList.contains('glass-float')).toBe(true)
    wrapper.unmount()
  })
})
