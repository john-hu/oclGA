import numpy
import pyopencl as cl

from simple_gene import SimpleGene

class SimpleChromosome:
    # SimpleChromosome - a chromosome contains a list of Genes.
    # __genes - a list of Genes
    # __name - name of the chromosome
    # dna - an listed of Gene's dna
    # dna_total_length - sum of the lenght of all genes's dna
    def __init__(self, genes, name = ""):
        assert all(isinstance(gene, SimpleGene) for gene in genes)
        assert type(genes) == list
        self.__genes = genes
        self.__name = name
        self.__improving_func = None
        self.__best = numpy.zeros(1, dtype=numpy.float32)
        self.__worst = numpy.zeros(1, dtype=numpy.float32)
        self.__avg = numpy.zeros(1, dtype=numpy.float32)

    @property
    def num_of_genes(self):
        return len(self.__genes)

    @property
    def name(self):
        return self.__name

    @property
    def dna_total_length(self):
        return self.num_of_genes

    @property
    def dna(self):
        return [gene.dna for gene in self.__genes]

    @dna.setter
    def dna(self, dna):
        assert self.num_of_genes == len(dna)
        for i, gene in enumerate(self.__genes):
            gene.dna = dna[i]

    @property
    def genes(self):
        return self.__genes

    @property
    def gene_elements(self):
        return [] if len(self.__genes) == 0 else self.__genes[0].elements

    @property
    def gene_elements_in_kernel(self):
        return [] if len(self.__genes) == 0 else self.__genes[0].elements_in_kernel

    @property
    def kernel_file(self):
        return "simple_chromosome.c"

    @property
    def struct_name(self):
        return "__SimpleChromosome";

    @property
    def chromosome_size_define(self):
        return "SIMPLE_CHROMOSOME_GENE_SIZE"

    @property
    def early_terminated(self):
        return abs(self.__worst[0] - self.__best[0]) < 0.0001

    def from_kernel_value(self, data):
        assert len(data) == self.num_of_genes
        genes = [self.__genes[idx].from_kernel_value(v) for idx, v in enumerate(data)]
        return SimpleChromosome(genes, self.__name)

    def kernelize(self):
        elements_size_list = [str(gene.elements_length) for gene in self.__genes]
        candidates = "#define SIMPLE_CHROMOSOME_GENE_ELEMENTS_SIZE {" +\
                            ", ".join(elements_size_list) + "}\n"
        defines = "#define SIMPLE_CHROMOSOME_GENE_SIZE " + str(self.num_of_genes) + "\n" +\
                  "#define SIMPLE_CHROMOSOME_GENE_MUTATE_FUNC " +\
                        self.__genes[0].mutate_func_name + "\n"

        return candidates + defines

    def save(self, data, ctx, queue, population):
        total_dna_size = population * self.dna_total_length
        # prepare memory
        other_chromosomes = numpy.zeros(total_dna_size, dtype=numpy.int32)
        ratios = numpy.zeros(population, dtype=numpy.float32)
        # read data from cl
        cl.enqueue_read_buffer(queue, self.__dev_ratios, ratios)
        cl.enqueue_read_buffer(queue, self.__dev_best, self.__best)
        cl.enqueue_read_buffer(queue, self.__dev_worst, self.__worst)
        cl.enqueue_read_buffer(queue, self.__dev_avg, self.__avg)
        cl.enqueue_read_buffer(queue, self.__dev_other_chromosomes, other_chromosomes).wait()
        # save all of them
        data["best"] = self.__best
        data["worst"] = self.__worst
        data["avg"] = self.__avg
        data["other_chromosomes"] = other_chromosomes
        data["ratios"] = ratios

    def restore(self, data, ctx, queue, population):
        self.__best = data["best"]
        self.__worst = data["worst"]
        self.__avg = data["avg"]
        other_chromosomes = data["other_chromosomes"]
        ratios = data["ratios"]
        # prepare CL memory
        mf = cl.mem_flags
        self.__dev_ratios = cl.Buffer(ctx, mf.WRITE_ONLY, ratios.nbytes)
        self.__dev_best = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                    hostbuf=self.__best)
        self.__dev_worst = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                     hostbuf=self.__worst)
        self.__dev_avg = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                   hostbuf=self.__avg)
        self.__dev_other_chromosomes = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                                 hostbuf=other_chromosomes)
        # Copy data from main memory to GPU memory
        cl.enqueue_copy(queue, self.__dev_ratios, ratios)
        cl.enqueue_copy(queue, self.__dev_best, self.__best)
        cl.enqueue_copy(queue, self.__dev_worst, self.__worst)
        cl.enqueue_copy(queue, self.__dev_avg, self.__avg)
        cl.enqueue_copy(queue, self.__dev_other_chromosomes, other_chromosomes)

    def preexecute_kernels(self, ctx, queue, population):
        ## initialize global variables for kernel execution
        total_dna_size = population * self.dna_total_length

        other_chromosomes = numpy.zeros(total_dna_size, dtype=numpy.int32)
        ratios = numpy.zeros(population, dtype=numpy.float32)

        mf = cl.mem_flags

        self.__dev_ratios = cl.Buffer(ctx, mf.WRITE_ONLY, ratios.nbytes)
        self.__dev_best = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                    hostbuf=self.__best)
        self.__dev_worst = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                     hostbuf=self.__worst)
        self.__dev_avg = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                   hostbuf=self.__avg)
        self.__dev_other_chromosomes = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR,
                                                 hostbuf=other_chromosomes)

    def get_current_best(self):
        return self.__best[0]

    def get_current_worst(self):
        return self.__worst[0]

    def get_current_avg(self):
        return self.__avg[0]

    def get_populate_kernel_names(self):
        return ["simple_chromosome_populate"]

    def get_crossover_kernel_names(self):
        return ["simple_chromosome_calc_ratio",\
                "simple_chromosome_pick_chromosomes",\
                "simple_chromosome_do_crossover"]

    def get_mutation_kernel_names(self):
        return ["simple_chromosome_mutate_all"]

    def execute_populate(self, prg, queue, population, dev_chromosomes, dev_rnum):
        prg.simple_chromosome_populate(queue,
                                       (population,),
                                       (1,),
                                       dev_chromosomes,
                                       dev_rnum).wait()

    def execute_crossover(self, prg, queue, population, generation_idx, prob_crossover,
                          dev_chromosomes, dev_fitnesses, dev_rnum):
        prg.simple_chromosome_calc_ratio(queue,
                                         (1,),
                                         (1,),
                                         dev_fitnesses,
                                         self.__dev_ratios,
                                         self.__dev_best,
                                         self.__dev_worst,
                                         self.__dev_avg).wait()

        cl.enqueue_read_buffer(queue, self.__dev_best, self.__best)
        cl.enqueue_read_buffer(queue, self.__dev_avg, self.__avg)
        cl.enqueue_read_buffer(queue, self.__dev_worst, self.__worst).wait()

        if self.early_terminated:
            return

        prg.simple_chromosome_pick_chromosomes(queue,
                                               (population,),
                                               (1,),
                                               dev_chromosomes,
                                               dev_fitnesses,
                                               self.__dev_other_chromosomes,
                                               self.__dev_ratios,
                                               dev_rnum).wait()
        prg.simple_chromosome_do_crossover(queue,
                                             (population,),
                                             (1,),
                                             dev_chromosomes,
                                             dev_fitnesses,
                                             self.__dev_other_chromosomes,
                                             self.__dev_best,
                                             numpy.float32(prob_crossover),
                                             dev_rnum,
                                             numpy.int32(generation_idx)).wait()


    def execute_mutation(self, prg, queue, population, generation_idx, prob_mutate,
                         dev_chromosomes, dev_fitnesses, dev_rnum):
        prg.simple_chromosome_mutate_all(queue,
                                         (population,),
                                         (1,),
                                         dev_chromosomes,
                                         numpy.float32(prob_mutate),
                                         dev_rnum).wait()
