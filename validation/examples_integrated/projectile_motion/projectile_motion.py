
import matplotlib
matplotlib.use('Agg')
import os
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import numpy as np
import ismo.iterative_surrogate_model_optimization
import ismo.train.trainer_factory
import ismo.train.multivariate_trainer
import ismo.samples.sample_generator_factory
import ismo.optimizers
import matplotlib.pyplot as plt
import plot_info
from objective import Objective
from ball import simulate
import collections

class LossWriter:
    def __init__(self, basename):
        self.basename = basename
        self.iteration = 0

    def __call__(self, loss):
        np.save(f'{self.basename}_iteration_{self.iteration}.npy', loss.history['loss'])
        f = plt.figure(self.iteration)

        plt.semilogy(loss.history['loss'])
        plt.xlabel('Epoch')
        plt.ylabel("Loss")
        f.savefig(f'{self.basename}_iteration_{self.iteration}.png')
        plt.close(f)
        self.iteration += 1


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="""
Runs the projectile motion
        """)

    parser.add_argument('--number_of_samples_per_iteration', type=int, nargs='+', default=[16, 4, 4, 4, 4, 4],
                        help='Number of samples per iteration')

    parser.add_argument('--generator', type=str, default='monte-carlo',
                        help='Generator')

    parser.add_argument('--simple_configuration_file', type=str, default='training_parameters.json',
                        help='Configuration of training and network')

    parser.add_argument('--optimizer', type=str, default='L-BFGS-B',
                        help='Configuration of training and network')

    parser.add_argument('--retries', type=int, default=1,
                        help='Number of retries (to get mean/variance). This option is studying how well it works over multiple runs.')

    parser.add_argument('--save_result', action='store_true',
                        help='Save the result to file')

    parser.add_argument('--prefix', type=str, default="projectile_motion_experiment_",
                        help="Prefix to all filenames")

    parser.add_argument('--with_competitor', action='store_true',
                        help='Also run the standard DNN+Opt competitor to see how well ISMO is doing in comparison')

    args = parser.parse_args()
    prefix = args.prefix


    all_values_min = collections.defaultdict(list)

    samples_as_str = "_".join(map(str, args.number_of_samples_per_iteration))
    for try_number in range(args.retries):
        print(f"try_number: {try_number}")
        generator = ismo.samples.create_sample_generator(args.generator)

        optimizer = ismo.optimizers.create_optimizer(args.optimizer)

        trainers =[ismo.train.create_trainer_from_simple_file(args.simple_configuration_file) for _ in range(1)]
        for trainer in trainers:
            trainer.add_loss_history_writer(LossWriter(f'{prefix}loss_try_{try_number}'))
        trainer = ismo.train.MultiVariateTrainer(
            trainers
            )
        objective = Objective()
        parameters, values = ismo.iterative_surrogate_model_optimization(
            number_of_samples_per_iteration=args.number_of_samples_per_iteration,
            sample_generator=generator,
            trainer=trainer,
            optimizer=optimizer,
            simulator=simulate,
            objective_function=objective,
            dimension=2,
            starting_sample=try_number*sum(args.number_of_samples_per_iteration))

        values = np.array(values)

        objective_values = [objective(values[i, 0], values[i, 1], values[i, 2]) for i in range(values.shape[0])]

        per_iteration = collections.defaultdict(list)

        total_number_of_samples = 0
        for number_of_samples in args.number_of_samples_per_iteration:
            total_number_of_samples += number_of_samples
            arg_min = np.argmin(objective_values[:total_number_of_samples])

            per_iteration['length'].append(values[arg_min])
            per_iteration['objective'].append(objective_values[arg_min])

        all_values_min['objective'].append(per_iteration['objective'])


        if args.save_result:
            np.savetxt(f'{prefix}parameters_{try_number}_samples_{samples_as_str}.txt', parameters)
            np.savetxt(f'{prefix}values_{try_number}_samples_{samples_as_str}.txt', values)
            np.savetxt(f'{prefix}objective_values_{try_number}_samples_{samples_as_str}.txt', objective_values)

    if args.with_competitor:
        competitor_min_values = collections.defaultdict(lambda : np.zeros((args.retries, len(args.number_of_samples_per_iteration)-1)))
        for try_number in range(args.retries):
            
            print(f"try_number (competitor): {try_number}")
            
            for iteration_number, number_of_samples_post in enumerate(args.number_of_samples_per_iteration[1:]):
                number_of_samples = sum(args.number_of_samples_per_iteration[:iteration_number+1])
                generator = ismo.samples.create_sample_generator(args.generator)
        
                optimizer = ismo.optimizers.create_optimizer(args.optimizer)

                trainers = [ismo.train.create_trainer_from_simple_file(args.simple_configuration_file) for _ in
                            range(1)]
                for trainer in trainers:
                    trainer.add_loss_history_writer(LossWriter(f'{prefix}loss_competitor_iteration_{iteration_number}_try_{try_number}'))
                trainer = ismo.train.MultiVariateTrainer(
                    trainers
                )
        
                parameters, values = ismo.iterative_surrogate_model_optimization(
                    number_of_samples_per_iteration=[number_of_samples, number_of_samples_post],
                    sample_generator=generator,
                    trainer=trainer,
                    optimizer=optimizer,
                    simulator=simulate,
                    objective_function=Objective(),
                    dimension=2,
                    starting_sample=try_number*(number_of_samples_post+number_of_samples))
                values = np.array(values)
                cobjective_values = [objective(values[i, 0], values[i, 1], values[i, 2]) for i in range(values.shape[0])]

                arg_min = np.argmin(objective_values)

                competitor_min_values['objective'][try_number, iteration_number] = objective_values[arg_min]


                competitor_min_values['length'].append(values[arg_min])

    
                if args.save_result:
                    np.savetxt(f'{prefix}competitor_parameters_{try_number}_it_{iteration_number}_samples_{samples_as_str}.txt', parameters)
                    np.savetxt(f'{prefix}competitor_values_{try_number}_it_{iteration_number}_samples_{samples_as_str}.txt', values)
                    np.savetxt(f'{prefix}competitor_objective_values_{try_number}_it_{iteration_number}_samples_{samples_as_str}.txt',
                        objective_values)

    print("Done!")
    iterations = np.arange(0, len(args.number_of_samples_per_iteration))
    for name, values in all_values_min.items():
        plt.errorbar(iterations, np.mean(values, 0),
                     yerr=np.std(values, 0), fmt='o',
                     label='ISMO')

        if args.with_competitor:
            plt.errorbar(iterations[:-1], np.mean(competitor_min_values[name], 0),
                         yerr=np.std(competitor_min_values[name], 0), fmt='*',
                         label='DNN+Opt')
        plt.legend()
        plt.xlabel('Iteration')
        plt.ylabel('Min value')
        plt.title(name)

        plot_info.savePlot(f'{prefix}optimized_value_{name}_{samples_as_str}')
